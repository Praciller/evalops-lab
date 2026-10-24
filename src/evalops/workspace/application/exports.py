"""In-memory, non-publishing preview of explicitly owner-classified run evidence.

This boundary delegates all public field selection and text checks to the
existing Public Evidence Contract V1 adapter, models and serializer.
"""

from __future__ import annotations

import hashlib
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from evalops.export.adapters import adapt_evaluation_result
from evalops.export.models import ClaimScope, DataKind
from evalops.export.serialization import serialize_public_artifact
from evalops.workspace.export.models import (
    ExportClassification,
    ExportPreview,
    PreviewFile,
    WorkspaceExportDataKind,
)
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

PREVIEW_LIFETIME = timedelta(minutes=15)
_RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")

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
