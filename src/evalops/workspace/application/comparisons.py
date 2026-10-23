"""Private Phase 6.3 use-cases for pinned, immutable evaluation baselines."""

from __future__ import annotations

from datetime import UTC, datetime

from evalops.workspace.models import BaselinePointer, WorkspaceState
from evalops.workspace.storage import WorkspaceStore


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
