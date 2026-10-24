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
    ExportClassification,
    ExportPreview,
    PreviewFile,
    WorkspaceExportDataKind,
)
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

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
            candidate_snapshot = self._store.get_run_snapshot(
                workspace_id, record.candidate_run_id
            )
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
                f"{artifact_id}/baseline.json": serialize_public_artifact(base_public).encode("utf-8"),
                f"{artifact_id}/candidate.json": serialize_public_artifact(candidate_public).encode("utf-8"),
                f"{artifact_id}/comparison.json": serialize_public_artifact(comparison_public).encode("utf-8"),
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
