"""Crash-safe local JSON storage for the Workspace registry."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

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
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class WorkspaceStore:
    """Persist only workspace metadata below an explicit local root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._registry_path = root / "registry.json"
        self._workspaces_path = root / "workspaces"

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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceStorageError("workspace metadata is unreadable") from error
    if not isinstance(payload, dict):
        raise WorkspaceStorageError("workspace metadata must be a JSON object")
    return payload


def _require_schema(payload: Mapping[str, object], expected: str) -> None:
    if payload.get("schema_version") != expected:
        raise UnsupportedSchemaVersionError("workspace metadata schema is unsupported")
