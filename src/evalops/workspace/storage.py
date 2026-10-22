"""Crash-safe local JSON storage for the Workspace registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from evalops.workspace.ingestion.models import InputKind, InputManifest, InputSourceMode
from evalops.workspace.jobs.models import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidJobTransitionError,
    JobRecord,
    JobState,
    SafeJobError,
)
from evalops.workspace.models import (
    WORKSPACE_REGISTRY_SCHEMA_VERSION,
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceRecord,
    WorkspaceRegistry,
)


class WorkspaceStorageError(Exception):
    """Base error for safe, user-facing Workspace storage failures."""


class DuplicateWorkspaceError(WorkspaceStorageError):
    """The registry contains the same workspace ID more than once."""


class UnknownWorkspaceError(WorkspaceStorageError):
    """A referenced workspace is not registered or is missing on disk."""


class UnsupportedSchemaVersionError(WorkspaceStorageError):
    """A persisted document uses a schema version this runtime cannot read."""


class UnknownInputError(WorkspaceStorageError):
    """A requested input does not belong to the selected workspace."""


_INPUT_ID_RE = re.compile(r"^input-[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
_JOB_ID_RE = re.compile(r"^job-[0-9a-f]{32}$")

if TYPE_CHECKING:
    from evalops.workspace.application.runs import RunSnapshot


def _replace_with_windows_retry(source: Path, destination: Path) -> None:
    """Retry brief Windows file-sharing locks, preserving atomic replace semantics."""

    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 7:
                raise
            time.sleep(0.005 * (attempt + 1))


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_windows_retry(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary_path = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_windows_retry(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_create_bytes(path: Path, data: bytes) -> None:
    """Atomically create immutable content without overwriting an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary_path = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Same-filesystem hard link is an atomic create-if-absent on NTFS/POSIX.
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise WorkspaceStorageError("immutable workspace record already exists") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_create_json(path: Path, payload: Mapping[str, object]) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _atomic_create_bytes(path, data)


class WorkspaceStore:
    """Persist only Workspace-owned metadata below an explicit local root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._registry_path = root / "registry.json"
        self._workspaces_path = root / "workspaces"
        self._job_lock = threading.RLock()

    def initialize(self) -> None:
        self._workspaces_path.mkdir(parents=True, exist_ok=True)
        if not self._registry_path.exists():
            _atomic_write_json(
                self._registry_path,
                WorkspaceRegistry(
                    schema_version=WORKSPACE_REGISTRY_SCHEMA_VERSION,
                    workspace_ids=[],
                ).model_dump(mode="json"),
            )
        else:
            self._load_registry()

    def list_workspaces(self) -> list[WorkspaceRecord]:
        registry = self._load_registry()
        return [self._load_workspace(workspace_id) for workspace_id in registry.workspace_ids]

    def create_workspace(self, display_name: str) -> WorkspaceRecord:
        self.initialize()
        normalized_name = _normalize_display_name(display_name)
        registry = self._load_registry()
        workspace_id = self._new_workspace_id(set(registry.workspace_ids))
        now = datetime.now(UTC)
        record = WorkspaceRecord(
            schema_version=WORKSPACE_SCHEMA_VERSION,
            workspace_id=workspace_id,
            display_name=normalized_name,
            created_at=now,
            updated_at=now,
        )
        _atomic_write_json(self._workspace_path(workspace_id), record.model_dump(mode="json"))
        _atomic_write_json(
            self._registry_path,
            WorkspaceRegistry(
                schema_version=WORKSPACE_REGISTRY_SCHEMA_VERSION,
                workspace_ids=sorted([*registry.workspace_ids, workspace_id]),
            ).model_dump(mode="json"),
        )
        return record

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord:
        registry = self._load_registry()
        if workspace_id not in registry.workspace_ids:
            raise UnknownWorkspaceError("workspace is not registered")
        return self._load_workspace(workspace_id)

    def rename_workspace(self, workspace_id: str, display_name: str) -> WorkspaceRecord:
        current = self.get_workspace(workspace_id)
        renamed = current.model_copy(
            update={
                "display_name": _normalize_display_name(display_name),
                "updated_at": datetime.now(UTC),
            }
        )
        _atomic_write_json(self._workspace_path(workspace_id), renamed.model_dump(mode="json"))
        return renamed

    def list_inputs(self, workspace_id: str) -> list[InputManifest]:
        self.get_workspace(workspace_id)
        directory = self._input_section(workspace_id, "manifests")
        if not directory.exists():
            return []
        return [
            self.get_input(workspace_id, path.stem) for path in sorted(directory.glob("*.json"))
        ]

    def get_input(self, workspace_id: str, input_id: str) -> InputManifest:
        self.get_workspace(workspace_id)
        path = self._input_manifest_path(workspace_id, input_id)
        if not path.is_file() or path.is_symlink():
            raise UnknownInputError("input is not registered in this workspace")
        payload = _read_json(path)
        _require_schema(payload, "workspace-input-v1")
        try:
            manifest = InputManifest.model_validate(payload)
        except ValidationError as error:
            raise WorkspaceStorageError("input manifest is invalid") from error
        if manifest.input_id != input_id:
            raise WorkspaceStorageError("input manifest identity mismatch")
        return manifest

    def save_input_manifest(self, workspace_id: str, manifest: InputManifest) -> None:
        self.get_workspace(workspace_id)
        path = self._input_manifest_path(workspace_id, manifest.input_id)
        if path.exists() or path.is_symlink():
            raise WorkspaceStorageError("input manifest is already registered")
        if manifest.source_mode == InputSourceMode.IMPORTED:
            expected = f"inputs/imported/{manifest.input_id}.jsonl"
            if manifest.stored_relative_path != expected or manifest.source_path is not None:
                raise WorkspaceStorageError("invalid imported input manifest")
            if not self._imported_path(workspace_id, manifest.input_id).is_file():
                raise WorkspaceStorageError("imported input content is missing")
        elif manifest.source_path is None or manifest.stored_relative_path is not None:
            raise WorkspaceStorageError("invalid referenced input manifest")
        _atomic_create_json(path, manifest.model_dump(mode="json"))

    def save_imported_input(self, workspace_id: str, input_id: str, data: bytes) -> str:
        self.get_workspace(workspace_id)
        path = self._imported_path(workspace_id, input_id)
        if path.exists() or path.is_symlink():
            raise WorkspaceStorageError("imported input already exists")
        _atomic_create_bytes(path, data)
        return f"inputs/imported/{input_id}.jsonl"

    def discard_imported_input(self, workspace_id: str, input_id: str) -> None:
        self.get_workspace(workspace_id)
        self._imported_path(workspace_id, input_id).unlink(missing_ok=True)

    def read_input_bytes(self, workspace_id: str, input_id: str) -> bytes:
        """Read an owned source, refusing checksum drift before run creation/execution."""

        manifest = self.get_input(workspace_id, input_id)
        try:
            if manifest.source_mode == InputSourceMode.IMPORTED:
                path = self._imported_path(workspace_id, input_id)
                if path.is_symlink() or not path.is_file():
                    raise WorkspaceStorageError("imported input content is unavailable")
            else:
                if manifest.source_path is None:
                    raise WorkspaceStorageError("referenced input has no source")
                path = Path(manifest.source_path).resolve(strict=True)
                if not path.is_file():
                    raise WorkspaceStorageError("referenced input content is unavailable")
            data = path.read_bytes()
        except (OSError, RuntimeError) as error:
            raise WorkspaceStorageError("registered input cannot be read") from error
        if hashlib.sha256(data).hexdigest() != manifest.content_sha256:
            raise WorkspaceStorageError("registered input checksum has changed")
        return data

    def save_run_snapshot(self, workspace_id: str, snapshot: RunSnapshot) -> None:
        """Create, but never replace, an owned immutable run config."""

        self.get_workspace(workspace_id)
        if snapshot.workspace_id != workspace_id or snapshot.config.run_id != snapshot.run_id:
            raise WorkspaceStorageError("run snapshot ownership or identity mismatch")
        for input_id, expected_hash, expected_kind in (
            (
                snapshot.ground_truth_input_id,
                snapshot.ground_truth_content_sha256,
                InputKind.RETRIEVAL_GROUND_TRUTH,
            ),
            (
                snapshot.predictions_input_id,
                snapshot.predictions_content_sha256,
                InputKind.RETRIEVAL_PREDICTIONS,
            ),
        ):
            manifest = self.get_input(workspace_id, input_id)
            if manifest.kind != expected_kind or manifest.content_sha256 != expected_hash:
                raise WorkspaceStorageError("run snapshot input integrity mismatch")
        path = self._run_config_path(workspace_id, snapshot.run_id)
        if path.exists() or path.is_symlink():
            raise WorkspaceStorageError("run snapshot already exists")
        _atomic_create_json(path, snapshot.model_dump(mode="json"))

    def get_run_snapshot(self, workspace_id: str, run_id: str) -> RunSnapshot:
        """Load only the current workspace's persisted, versioned run snapshot."""

        from evalops.workspace.application.runs import RunSnapshot

        self.get_workspace(workspace_id)
        path = self._run_config_path(workspace_id, run_id)
        if not path.is_file() or path.is_symlink():
            raise WorkspaceStorageError("run snapshot is unavailable")
        payload = _read_json(path)
        _require_schema(payload, "workspace-run-v1")
        try:
            snapshot = RunSnapshot.model_validate(payload)
        except ValidationError as error:
            raise WorkspaceStorageError("run snapshot is invalid") from error
        if snapshot.workspace_id != workspace_id or snapshot.run_id != run_id:
            raise WorkspaceStorageError("run snapshot ownership or identity mismatch")
        if snapshot.config.run_id != run_id:
            raise WorkspaceStorageError("run snapshot config identity mismatch")
        return snapshot

    def _run_config_path(self, workspace_id: str, run_id: str) -> Path:
        if not _RUN_ID_RE.fullmatch(run_id):
            raise WorkspaceStorageError("run identifier is invalid")
        workspace_root = (self._workspaces_path / workspace_id).resolve()
        if not workspace_root.is_relative_to(self._workspaces_path.resolve()):
            raise WorkspaceStorageError("workspace directory is unsafe")
        runs_root = workspace_root / "runs"
        if not runs_root.resolve().is_relative_to(workspace_root):
            raise WorkspaceStorageError("workspace runs directory is unsafe")
        directory = runs_root / run_id
        if not directory.resolve().is_relative_to(runs_root.resolve()):
            raise WorkspaceStorageError("run directory is unsafe")
        return directory / "config.json"

    def _jobs_directory(self, workspace_id: str) -> Path:
        self.get_workspace(workspace_id)
        workspace_root = (self._workspaces_path / workspace_id).resolve()
        if not workspace_root.is_relative_to(self._workspaces_path.resolve()):
            raise WorkspaceStorageError("workspace directory is unsafe")
        directory = workspace_root / "jobs"
        if not directory.resolve().is_relative_to(workspace_root):
            raise WorkspaceStorageError("workspace jobs directory is unsafe")
        return directory

    def _job_path(self, workspace_id: str, job_id: str) -> Path:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise WorkspaceStorageError("invalid job identifier")
        directory = self._jobs_directory(workspace_id)
        child = directory / job_id
        if not child.resolve().is_relative_to(directory.resolve()):
            raise WorkspaceStorageError("job directory is unsafe")
        return child / "job.json"

    def save_job_record(self, job: JobRecord) -> None:
        """Persist only a brand-new QUEUED job belonging to an existing run."""
        with self._job_lock:
            snapshot = self.get_run_snapshot(job.workspace_id, job.run_id)
            if snapshot.workspace_id != job.workspace_id:
                raise WorkspaceStorageError("job workspace does not match its run")
            if job.state != JobState.QUEUED or job.revision != 0 or job.cancel_requested:
                raise WorkspaceStorageError("new jobs must begin in QUEUED state")
            path = self._job_path(job.workspace_id, job.job_id)
            if path.exists() or path.is_symlink():
                raise WorkspaceStorageError("job already exists")
            _atomic_create_json(path, job.model_dump(mode="json"))

    def get_job_record(self, workspace_id: str, job_id: str) -> JobRecord:
        self.get_workspace(workspace_id)
        path = self._job_path(workspace_id, job_id)
        if not path.is_file() or path.is_symlink():
            raise WorkspaceStorageError("job is unavailable")
        payload = _read_json(path)
        _require_schema(payload, "workspace-job-v1")
        try:
            record = JobRecord.model_validate(payload)
        except ValidationError as error:
            raise WorkspaceStorageError("job record is invalid") from error
        if record.job_id != job_id or record.workspace_id != workspace_id:
            raise WorkspaceStorageError("job identity mismatch")
        self.get_run_snapshot(workspace_id, record.run_id)
        return record

    def list_job_records(self, workspace_id: str) -> list[JobRecord]:
        directory = self._jobs_directory(workspace_id)
        if not directory.exists():
            return []
        if not directory.is_dir():
            raise WorkspaceStorageError("job storage is invalid")
        records = []
        for path in sorted(directory.iterdir()):
            if not path.is_dir() or path.is_symlink():
                raise WorkspaceStorageError("unexpected job storage entry")
            records.append(self.get_job_record(workspace_id, path.name))
        return sorted(records, key=lambda record: (record.created_at, record.job_id))

    def find_job_record(self, job_id: str) -> JobRecord:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise WorkspaceStorageError("invalid job identifier")
        matching = [
            record
            for workspace in self.list_workspaces()
            for record in self.list_job_records(workspace.workspace_id)
            if record.job_id == job_id
        ]
        if len(matching) != 1:
            raise WorkspaceStorageError("job is unavailable or ambiguous")
        return matching[0]

    def update_job_record(
        self,
        workspace_id: str,
        job_id: str,
        *,
        expected_revision: int,
        next_state: JobState | None = None,
        cancel_requested: bool | None = None,
        safe_error: SafeJobError | None = None,
    ) -> JobRecord:
        """Atomically validate and advance exactly one persisted revision."""
        with self._job_lock:
            current = self.get_job_record(workspace_id, job_id)
            if current.revision != expected_revision:
                raise InvalidJobTransitionError("stale job revision")
            if current.state in TERMINAL_STATES:
                raise InvalidJobTransitionError("terminal job cannot be modified")
            target = current.state if next_state is None else next_state
            if next_state is not None and target not in ALLOWED_TRANSITIONS[current.state]:
                raise InvalidJobTransitionError("unsupported job state transition")
            cancel = current.cancel_requested if cancel_requested is None else cancel_requested
            if current.cancel_requested and not cancel:
                raise InvalidJobTransitionError("cancellation cannot be withdrawn")
            if current.cancel_requested and target not in {
                current.state,
                JobState.CANCELLED,
                JobState.FAILED,
                JobState.INTERRUPTED,
            }:
                raise InvalidJobTransitionError("cancelled job cannot advance")
            if safe_error is not None and target not in {JobState.FAILED, JobState.INTERRUPTED}:
                raise InvalidJobTransitionError("safe error requires failed or interrupted state")
            if target == JobState.FAILED and safe_error is None:
                raise InvalidJobTransitionError("failed job requires a safe error")
            if target == current.state and cancel == current.cancel_requested:
                raise InvalidJobTransitionError("job update is a no-op")
            updated = JobRecord.model_validate(
                {
                    **current.model_dump(mode="python"),
                    "state": target,
                    "revision": current.revision + 1,
                    "cancel_requested": cancel,
                    "safe_error": safe_error,
                    "updated_at": datetime.now(UTC),
                }
            )
            _atomic_write_json(
                self._job_path(workspace_id, job_id), updated.model_dump(mode="json")
            )
            return updated

    def _inputs_directory(self, workspace_id: str) -> Path:
        workspace_root = (self._workspaces_path / workspace_id).resolve()
        if not workspace_root.is_relative_to(self._workspaces_path.resolve()):
            raise WorkspaceStorageError("workspace directory is unsafe")
        directory = workspace_root / "inputs"
        if not directory.resolve().is_relative_to(workspace_root):
            raise WorkspaceStorageError("workspace input directory is unsafe")
        return directory

    def _input_section(self, workspace_id: str, section: str) -> Path:
        base = self._inputs_directory(workspace_id)
        candidate = base / section
        if not candidate.resolve().is_relative_to(base.resolve()):
            raise WorkspaceStorageError("workspace input section is unsafe")
        return candidate

    def _input_manifest_path(self, workspace_id: str, input_id: str) -> Path:
        if not _INPUT_ID_RE.fullmatch(input_id):
            raise UnknownInputError("invalid input identifier")
        return self._input_section(workspace_id, "manifests") / f"{input_id}.json"

    def _imported_path(self, workspace_id: str, input_id: str) -> Path:
        if not _INPUT_ID_RE.fullmatch(input_id):
            raise UnknownInputError("invalid input identifier")
        return self._input_section(workspace_id, "imported") / f"{input_id}.jsonl"

    def _load_registry(self) -> WorkspaceRegistry:
        if not self._registry_path.is_file():
            raise WorkspaceStorageError("workspace registry is unavailable")
        payload = _read_json(self._registry_path)
        _require_schema(payload, WORKSPACE_REGISTRY_SCHEMA_VERSION)
        try:
            registry = WorkspaceRegistry.model_validate(payload)
        except ValidationError as error:
            raise WorkspaceStorageError("workspace registry is invalid") from error
        if len(registry.workspace_ids) != len(set(registry.workspace_ids)):
            raise DuplicateWorkspaceError("workspace registry contains duplicate IDs")
        return registry

    def _load_workspace(self, workspace_id: str) -> WorkspaceRecord:
        path = self._workspace_path(workspace_id)
        if not path.is_file():
            raise UnknownWorkspaceError("registered workspace metadata is missing")
        payload = _read_json(path)
        _require_schema(payload, WORKSPACE_SCHEMA_VERSION)
        try:
            return WorkspaceRecord.model_validate(payload)
        except ValidationError as error:
            raise WorkspaceStorageError("workspace metadata is invalid") from error

    def _workspace_path(self, workspace_id: str) -> Path:
        return self._workspaces_path / workspace_id / "workspace.json"

    @staticmethod
    def _new_workspace_id(existing: set[str]) -> str:
        workspace_id = f"ws-{uuid.uuid4().hex}"
        while workspace_id in existing:
            workspace_id = f"ws-{uuid.uuid4().hex}"
        return workspace_id


def _normalize_display_name(display_name: str) -> str:
    normalized = display_name.strip()
    if not normalized:
        raise ValueError("workspace display name must not be empty")
    return normalized


def _read_json(path: Path) -> dict[str, object]:
    # Another Store instance/process can replace job.json between open() and
    # Windows sharing checks. Retry only transient file-sharing PermissionError.
    for attempt in range(8):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            break
        except PermissionError as error:
            if os.name != "nt" or attempt == 7:
                raise WorkspaceStorageError("workspace metadata is unreadable") from error
            time.sleep(0.005 * (attempt + 1))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceStorageError("workspace metadata is unreadable") from error
    if not isinstance(payload, dict):
        raise WorkspaceStorageError("workspace metadata must be a JSON object")
    return payload


def _require_schema(payload: Mapping[str, object], expected: str) -> None:
    if payload.get("schema_version") != expected:
        raise UnsupportedSchemaVersionError("workspace metadata schema is unsupported")
