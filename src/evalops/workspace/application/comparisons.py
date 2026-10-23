"""Private Phase 6.3 use-cases for pinned, immutable evaluation baselines."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from evalops.regression.comparison import compare_metrics
from evalops.workspace.comparison.compatibility import (
    assess_local_retrieval_compatibility,
    load_verified_population,
)
from evalops.workspace.comparison.failures import build_failure_transitions
from evalops.workspace.comparison.models import (
    ComparisonFailureArtifact,
    ComparisonCompatibility,
    ComparisonCompatibilityStatus,
    ComparisonMode,
    ComparisonRecord,
)
from evalops.workspace.comparison.policy import (
    WORKSPACE_RETRIEVAL_POLICY_VERSION,
    build_workspace_retrieval_rules,
)
from evalops.workspace.models import BaselinePointer, WorkspaceState
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore


class IncompatibleComparisonError(ValueError):
    """Canonical comparison requires trustworthy compatible operands."""

    def __init__(self, compatibility: ComparisonCompatibility) -> None:
        self.compatibility = compatibility
        super().__init__("retrieval operands are not comparable")


class ComparisonService:
    """Manage explicit local baseline identity, never mutate completed runs."""

    def __init__(self, store: WorkspaceStore) -> None:
        self._store = store

    def get_baseline(self, workspace_id: str) -> BaselinePointer | None:
        """Return the saved pointer or None; no implicit latest-run selection."""

        return self._store.get_workspace_state(workspace_id).baseline

    def set_baseline(self, workspace_id: str, run_id: str) -> WorkspaceState:
        """Pin only a single owned COMPLETE run with intact result/provenance.

        The authoritative storage read verifies terminal job state, ownership,
        run configuration and recorded SHA-256 against the current result bytes.
        Never trust a caller-supplied hash or alter immutable run artifacts.
        """

        _, provenance = self._store.get_run_artifacts(workspace_id, run_id)
        next_pointer = BaselinePointer(
            run_id=run_id,
            result_sha256=provenance.result_sha256,
            pinned_at=datetime.now(UTC),
        )
        current = self._store.get_workspace_state(workspace_id)
        updated = current.model_copy(update={"baseline": next_pointer})
        self._store.save_workspace_state(workspace_id, updated)
        return updated

    def create_comparison(
        self,
        workspace_id: str,
        candidate_run_id: str,
        *,
        mode: ComparisonMode,
    ) -> ComparisonRecord:
        """Freeze explicitly pinned identities and shared-regression decisions.

        Compatibility is derived only from server-owned, hash-verified input
        bytes and completed immutable run evidence. The caller cannot supply
        compatibility status, metric rules, policy version, or result hashes.
        """

        requested_mode = ComparisonMode(mode)
        pointer = self.get_baseline(workspace_id)
        if pointer is None:
            raise WorkspaceStorageError("no pinned workspace baseline")
        if candidate_run_id == pointer.run_id:
            raise ValueError("a run cannot be compared with itself")

        baseline_result, baseline_provenance = self._store.get_run_artifacts(
            workspace_id, pointer.run_id
        )
        candidate_result, candidate_provenance = self._store.get_run_artifacts(
            workspace_id, candidate_run_id
        )
        if baseline_provenance.result_sha256 != pointer.result_sha256:
            raise WorkspaceStorageError("pinned baseline result checksum has changed")

        baseline_snapshot = self._store.get_run_snapshot(workspace_id, pointer.run_id)
        candidate_snapshot = self._store.get_run_snapshot(workspace_id, candidate_run_id)
        baseline_population = load_verified_population(self._store, baseline_snapshot)
        candidate_population = load_verified_population(self._store, candidate_snapshot)
        compatibility = assess_local_retrieval_compatibility(
            baseline_snapshot,
            baseline_result,
            candidate_snapshot,
            candidate_result,
            baseline_population=baseline_population,
            candidate_population=candidate_population,
        )
        if (
            requested_mode == ComparisonMode.CANONICAL
            and compatibility.status != ComparisonCompatibilityStatus.COMPARABLE
        ):
            raise IncompatibleComparisonError(compatibility)

        report = compare_metrics(
            candidate_result.metrics,
            baseline_result.metrics,
            build_workspace_retrieval_rules(candidate_snapshot.config.top_k),
        )
        record = ComparisonRecord(
            comparison_id=f"comparison-{uuid.uuid4().hex}",
            workspace_id=workspace_id,
            mode=requested_mode,
            compatibility=compatibility,
            baseline_run_id=pointer.run_id,
            baseline_result_sha256=pointer.result_sha256,
            candidate_run_id=candidate_run_id,
            candidate_result_sha256=candidate_provenance.result_sha256,
            policy_version=WORKSPACE_RETRIEVAL_POLICY_VERSION,
            regression_report=report,
            created_at=datetime.now(UTC),
        )
        # Failure transitions only exist when both actual evaluator query sets
        # match. Exploratory comparisons across disjoint populations keep their
        # immutable delta report but have no fabricated per-query transitions.
        failure_artifact = None
        if (
            baseline_population.ground_truth_query_ids_fingerprint
            == candidate_population.ground_truth_query_ids_fingerprint
        ):
            failure_artifact = ComparisonFailureArtifact(
                comparison_id=record.comparison_id,
                transitions=build_failure_transitions(baseline_result, candidate_result),
            )
        self._store.save_comparison_record(
            workspace_id, record, failure_artifact=failure_artifact
        )
        return record
