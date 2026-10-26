"""In-memory, non-publishing preview of explicitly owner-classified run evidence.

This boundary delegates all public field selection and text checks to the
existing Public Evidence Contract V1 adapter, models and serializer.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import re
import shutil
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from evalops.export.adapters import (
    adapt_evaluation_result,
    adapt_regression_report,
    build_public_index,
)
from evalops.export.models import ClaimScope, DataKind, PopulationCompatibility
from evalops.export.serialization import serialize_public_artifact
from evalops.regression.comparison import compare_metrics
from evalops.workspace.comparison.compatibility import (
    assess_local_retrieval_compatibility,
    load_verified_population,
)
from evalops.workspace.comparison.models import (
    ComparisonCompatibilityStatus,
    ComparisonMode,
)
from evalops.workspace.comparison.policy import build_workspace_retrieval_rules
from evalops.workspace.export.models import (
    ConfirmExportRequest,
    ExportClassification,
    ExportedFile,
    ExportManifest,
    ExportPreview,
    PreviewFile,
    WorkspaceExportDataKind,
)
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore


def _explicit_destination(raw_path: str) -> Path:
    """Accept only an existing, explicitly named regular local directory."""

    if raw_path != raw_path.strip() or not raw_path.strip():
        raise ValueError("an explicit destination directory is required")
    destination = Path(raw_path)
    # Exports require an explicitly selected local directory. Never resolve a
    # UNC/device path that could contact a remote host under the app's identity.
    if (
        not destination.is_absolute()
        or raw_path.startswith(("\\\\", "//"))
        or destination.is_symlink()
    ):
        raise ValueError("destination must be an absolute non-symlink local directory")
    try:
        resolved = destination.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("destination directory is unavailable") from error
    if str(resolved).startswith(("\\\\", "//")):
        raise ValueError("destination must resolve to a local directory")
    if not resolved.is_dir():
        raise ValueError("destination must be an existing directory")
    return resolved


def _exclusive_directory_commit(staged: Path, target: Path) -> None:
    """Atomically publish a complete directory without replacing any target.

    Linux uses renameat2(RENAME_NOREPLACE); Windows os.rename refuses an
    existing directory. Other platforms fail closed rather than risking
    POSIX os.rename replacing an existing empty directory.
    """

    if os.name == "nt":
        staged.rename(target)
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOTSUP, "exclusive directory rename unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        at_fdcwd = -100
        no_replace = 1
        outcome = renameat2(
            at_fdcwd, os.fsencode(staged), at_fdcwd, os.fsencode(target), no_replace
        )
        if outcome != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))
        return
    raise OSError(errno.ENOTSUP, "exclusive directory rename unavailable")


def _write_export_files(destination: Path, files: Mapping[str, bytes]) -> Path:
    """Stage complete output on the same volume, refusing all overwrites."""

    if len(files) == 1:
        filename, content = next(iter(files.items()))
        if "/" in filename or "\\" in filename or not re.fullmatch(r"[a-z0-9-]+\.json", filename):
            raise ValueError("invalid run export filename")
        target = destination / filename
        if target.exists() or target.is_symlink():
            raise FileExistsError("export destination already exists")
        descriptor, name = tempfile.mkstemp(prefix=".evalops-export-", dir=destination)
        staged = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            # Hard-link creation is atomic and fails if the target appeared.
            os.link(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        return target

    if len(files) != 4:
        raise ValueError("invalid comparison export bundle")
    parts = [name.split("/") for name in files]
    folders = {part[0] for part in parts}
    basenames = {part[1] for part in parts if len(part) == 2}
    if (
        len(folders) != 1
        or any(len(part) != 2 for part in parts)
        or not re.fullmatch(r"[a-z0-9-]+", next(iter(folders)))
        or basenames != {"baseline.json", "candidate.json", "comparison.json", "index.json"}
    ):
        raise ValueError("invalid comparison export layout")
    target = destination / next(iter(folders))
    if target.exists() or target.is_symlink():
        raise FileExistsError("export bundle destination already exists")

    staged = Path(tempfile.mkdtemp(prefix=".evalops-bundle-", dir=destination))
    try:
        for name, data in sorted(files.items()):
            output_path = staged / name.split("/")[1]
            with output_path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        _exclusive_directory_commit(staged, target)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return target


PREVIEW_LIFETIME = timedelta(minutes=15)
_RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")
_COMPARISON_ID = re.compile(r"^comparison-[0-9a-f]{32}$")

# Disclose the actual allowlist boundary rather than claiming to clean raw files.
_EXCLUDED = [
    "Not in public contract: source files, original CSV, local file paths",
    "Not in public contract: job records, logs, session and bootstrap data",
    "Not in public contract: private evaluator details outside adapter allowlist",
]
_TRANSFORMED = [
    "Immutable EvaluationResult adapted into Public Evidence Contract V1",
    "Public model policy validated and canonically JSON serialized",
]


@dataclass(frozen=True)
class _PreparedExport:
    workspace_id: str
    expires_at: datetime
    source_type: Literal["run", "comparison"]
    source_id: str
    classification: ExportClassification
    files: Mapping[str, bytes]


class ExportService:
    """Keep canonical output bytes in process memory until explicit confirmation.

    No constructor or preview action creates files, publishes evidence, writes
    into apps/web, or infers a verification status from job completion.
    """

    def __init__(
        self,
        store: WorkspaceStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._prepared: dict[str, _PreparedExport] = {}
        self._lock = threading.RLock()

    def preview_run(
        self, workspace_id: str, run_id: str, classification: ExportClassification
    ) -> ExportPreview:
        """Return safe disclosure and manifest; never expose sanitized bytes yet."""

        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("invalid run identifier")
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("preview clock must be timezone-aware")
        expires_at = now + PREVIEW_LIFETIME
        preview_id = f"preview-{uuid.uuid4().hex}"
        kind = DataKind(classification.data_kind.value)
        scope = (
            ClaimScope.INTEGRATION_ONLY
            if classification.data_kind == WorkspaceExportDataKind.SYNTHETIC_FIXTURE
            else ClaimScope.PROTOCOL_SPECIFIC
        )

        try:
            result, _ = self._store.get_run_artifacts(workspace_id, run_id)
        except WorkspaceStorageError:
            return ExportPreview(
                preview_id=preview_id,
                source_type="run",
                source_id=run_id,
                eligible=False,
                blocking_reasons=["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"],
                output_files=[],
                included=[],
                removed=list(_EXCLUDED),
                transformed=[],
                classification=classification,
                expires_at=expires_at,
            )

        # The adapter is the sole source of public fields: do not manually
        # whitelist anything from run details or local provenance.
        try:
            artifact = adapt_evaluation_result(
                result,
                artifact_id=f"workspace-{run_id}",
                verification_status=classification.verification_status,
                data_kind=kind,
                claim_scope=scope,
                limitations=classification.limitations,
            )
            encoded = serialize_public_artifact(artifact).encode("utf-8")
        except (ValueError, ValidationError):
            # Never return the original exception, which may contain user metadata.
            return ExportPreview(
                preview_id=preview_id,
                source_type="run",
                source_id=run_id,
                eligible=False,
                blocking_reasons=["PUBLIC_EVIDENCE_POLICY_REJECTED"],
                output_files=[],
                included=[],
                removed=list(_EXCLUDED),
                transformed=[],
                classification=classification,
                expires_at=expires_at,
            )

        filename = f"workspace-{run_id}.json"
        manifest = PreviewFile(
            filename=filename,
            sha256=hashlib.sha256(encoded).hexdigest(),
            size_bytes=len(encoded),
        )
        included = ["Public run metadata", "Aggregate evaluator metrics"]
        if artifact.failures:
            included.append("Allowlisted failure categories")
        if artifact.evidence:
            included.append("Validated synthetic per-query evidence")

        with self._lock:
            self._purge_expired(now)
            self._prepared[preview_id] = _PreparedExport(
                workspace_id=workspace_id,
                expires_at=expires_at,
                source_type="run",
                source_id=run_id,
                classification=classification,
                files={filename: encoded},
            )

        return ExportPreview(
            preview_id=preview_id,
            source_type="run",
            source_id=run_id,
            eligible=True,
            blocking_reasons=[],
            output_files=[manifest],
            included=included,
            removed=list(_EXCLUDED),
            transformed=list(_TRANSFORMED),
            classification=classification,
            expires_at=expires_at,
        )

    def preview_comparison(
        self, workspace_id: str, comparison_id: str, classification: ExportClassification
    ) -> ExportPreview:
        """Preview only verified canonical comparisons, including both run operands.

        Never accept a compatibility flag from the caller or export the private
        Failure Explorer transition sidecar. Public adapters remain authoritative.
        """

        if not _COMPARISON_ID.fullmatch(comparison_id):
            raise ValueError("invalid comparison identifier")
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("preview clock must be timezone-aware")
        expires_at = now + PREVIEW_LIFETIME
        preview_id = f"preview-{uuid.uuid4().hex}"

        def blocked(reason: str) -> ExportPreview:
            return ExportPreview(
                preview_id=preview_id,
                source_type="comparison",
                source_id=comparison_id,
                eligible=False,
                blocking_reasons=[reason],
                output_files=[],
                included=[],
                removed=list(_EXCLUDED),
                transformed=[],
                classification=classification,
                expires_at=expires_at,
            )

        try:
            record = self._store.get_comparison_record(workspace_id, comparison_id)
        except WorkspaceStorageError:
            return blocked("SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID")

        # Do not touch run artifacts or call any public serializer for exploratory
        # comparisons: their incompatible populations are permanently private.
        if (
            record.mode != ComparisonMode.CANONICAL
            or record.compatibility.status != ComparisonCompatibilityStatus.COMPARABLE
        ):
            return blocked("NON_CANONICAL_COMPARISON")

        try:
            base, base_provenance = self._store.get_run_artifacts(
                workspace_id, record.baseline_run_id
            )
            candidate, candidate_provenance = self._store.get_run_artifacts(
                workspace_id, record.candidate_run_id
            )
            if (
                base.run.run_id != record.baseline_run_id
                or candidate.run.run_id != record.candidate_run_id
                or base_provenance.result_sha256 != record.baseline_result_sha256
                or candidate_provenance.result_sha256 != record.candidate_result_sha256
                or record.baseline_run_id == record.candidate_run_id
            ):
                return blocked("SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID")

            base_snapshot = self._store.get_run_snapshot(workspace_id, record.baseline_run_id)
            candidate_snapshot = self._store.get_run_snapshot(workspace_id, record.candidate_run_id)
            assessed = assess_local_retrieval_compatibility(
                base_snapshot,
                base,
                candidate_snapshot,
                candidate,
                baseline_population=load_verified_population(self._store, base_snapshot),
                candidate_population=load_verified_population(self._store, candidate_snapshot),
            )
            if assessed.status != ComparisonCompatibilityStatus.COMPARABLE:
                return blocked("SOURCE_POPULATION_INCOMPATIBLE")

            # The stored report must still equal the shared authoritative policy
            # applied to these immutable source operands.
            actual_report = compare_metrics(
                candidate.metrics,
                base.metrics,
                build_workspace_retrieval_rules(candidate_snapshot.config.top_k),
            )
            if actual_report != record.regression_report:
                return blocked("SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID")
        except (WorkspaceStorageError, ValueError, ValidationError):
            return blocked("SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID")

        kind = DataKind(classification.data_kind.value)
        scope = (
            ClaimScope.INTEGRATION_ONLY
            if classification.data_kind == WorkspaceExportDataKind.SYNTHETIC_FIXTURE
            else ClaimScope.PROTOCOL_SPECIFIC
        )
        artifact_id = f"workspace-{comparison_id}"
        baseline_id = f"{artifact_id}-baseline"
        candidate_id = f"{artifact_id}-candidate"
        try:
            base_public = adapt_evaluation_result(
                base,
                artifact_id=baseline_id,
                verification_status=classification.verification_status,
                data_kind=kind,
                claim_scope=scope,
                limitations=classification.limitations,
            )
            candidate_public = adapt_evaluation_result(
                candidate,
                artifact_id=candidate_id,
                verification_status=classification.verification_status,
                data_kind=kind,
                claim_scope=scope,
                limitations=classification.limitations,
            )
            comparison_public = adapt_regression_report(
                record.regression_report,
                artifact_id=artifact_id,
                baseline_artifact_id=baseline_id,
                candidate_artifact_id=candidate_id,
                baseline_run_id=record.baseline_run_id,
                candidate_run_id=record.candidate_run_id,
                verification_status=classification.verification_status,
                data_kind=kind,
                claim_scope=scope,
                limitations=classification.limitations,
                population_compatibility=PopulationCompatibility.MATCHED,
            )
            index = build_public_index([base_public, candidate_public, comparison_public])
            serialized = {
                f"{artifact_id}/baseline.json": serialize_public_artifact(base_public).encode(
                    "utf-8"
                ),
                f"{artifact_id}/candidate.json": serialize_public_artifact(candidate_public).encode(
                    "utf-8"
                ),
                f"{artifact_id}/comparison.json": serialize_public_artifact(
                    comparison_public
                ).encode("utf-8"),
                f"{artifact_id}/index.json": serialize_public_artifact(index).encode("utf-8"),
            }
        except (ValueError, ValidationError):
            # Do not expose private text in original model-validation errors.
            return blocked("PUBLIC_EVIDENCE_POLICY_REJECTED")

        manifest = [
            PreviewFile(
                filename=name,
                sha256=hashlib.sha256(contents).hexdigest(),
                size_bytes=len(contents),
            )
            for name, contents in serialized.items()
        ]
        included = [
            "Two public run summaries with aggregate metrics and safe metadata",
            "Shared-policy public regression report with matched population claim",
            "Explicit allowlisted public evidence index referencing both run artifacts",
        ]
        if base_public.evidence or candidate_public.evidence:
            included.append("Validated synthetic per-query evidence from the public run adapter")
        with self._lock:
            self._purge_expired(now)
            self._prepared[preview_id] = _PreparedExport(
                workspace_id=workspace_id,
                expires_at=expires_at,
                source_type="comparison",
                source_id=comparison_id,
                classification=classification,
                files=serialized,
            )
        return ExportPreview(
            preview_id=preview_id,
            source_type="comparison",
            source_id=comparison_id,
            eligible=True,
            blocking_reasons=[],
            output_files=manifest,
            included=included,
            removed=[
                *_EXCLUDED,
                "Not in public comparison contract: private Failure Explorer transition sidecar",
            ],
            transformed=list(_TRANSFORMED),
            classification=classification,
            expires_at=expires_at,
        )

    def confirm(self, workspace_id: str, request: ConfirmExportRequest) -> ExportManifest:
        """Commit an exact previously previewed snapshot, never auto-publish.

        This is a second explicit owner action. A fresh sanitized preview must
        match the exact cached bytes; any changed source is rejected.
        """

        with self._lock:
            now = self._clock()
            if now.tzinfo is None:
                raise ValueError("confirmation clock must be timezone-aware")
            self._purge_expired(now)
            prepared = self._prepared.get(request.preview_id)
            if prepared is None or prepared.workspace_id != workspace_id:
                raise LookupError("export preview is unavailable or expired")

            # Compare to a freshly verified source, not just the cached JSON.
            if prepared.source_type == "run":
                rechecked = self.preview_run(
                    workspace_id, prepared.source_id, prepared.classification
                )
            elif prepared.source_type == "comparison":
                rechecked = self.preview_comparison(
                    workspace_id, prepared.source_id, prepared.classification
                )
            else:
                raise ValueError("unsupported export source")
            try:
                fresh = self._prepared.get(rechecked.preview_id)
                if not rechecked.eligible or fresh is None or fresh.files != prepared.files:
                    raise ValueError("source changed since export preview")
            finally:
                self._prepared.pop(rechecked.preview_id, None)

            destination = _explicit_destination(request.destination_directory)
            try:
                target = _write_export_files(destination, prepared.files)
            except FileExistsError as error:
                raise ValueError("export destination already exists") from error

            files = [
                ExportedFile(
                    filename=name,
                    sha256=hashlib.sha256(contents).hexdigest(),
                    size_bytes=len(contents),
                )
                for name, contents in prepared.files.items()
            ]
            manifest = ExportManifest(
                export_id=f"export-{uuid.uuid4().hex}",
                source_type=prepared.source_type,
                source_id=prepared.source_id,
                destination=str(target),
                files=files,
                classification=prepared.classification,
                created_at=now,
            )
            # Private history records only completed destination writes. If
            # persistence fails, do not delete or overwrite user-owned output.
            self._store.save_export_manifest(
                workspace_id, manifest.export_id, manifest.model_dump(mode="json")
            )
            self._prepared.pop(request.preview_id, None)
            return manifest

    def get_prepared_files(self, workspace_id: str, preview_id: str) -> dict[str, bytes]:
        """Internal, owner-scoped copy for the later explicit confirmation use-case.

        This is not an API endpoint, filesystem action or publication method.
        """

        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            prepared = self._prepared.get(preview_id)
            if prepared is None or prepared.workspace_id != workspace_id:
                raise LookupError("export preview is unavailable or expired")
            return dict(prepared.files)

    def _purge_expired(self, now: datetime) -> None:
        for key, value in list(self._prepared.items()):
            if value.expires_at <= now:
                del self._prepared[key]
