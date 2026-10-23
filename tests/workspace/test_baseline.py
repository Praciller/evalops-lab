"""Phase 6.3 Task 1: private explicit baseline with integrity and ownership gates."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from evalops.workspace.application.comparisons import ComparisonService
from evalops.workspace.application.runs import CreateRetrievalRun, RetrievalRunService
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.jobs.models import JobState, SafeJobError
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

GT = b'{"query_id":"q1","relevant_document_ids":["doc1"]}\n'
PRED = b'{"query_id":"q1","retrieved_document_ids":["doc1"]}\n'


@pytest.fixture
def setup(tmp_path: Path) -> tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str]:
    root = tmp_path / "private"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("Baseline fixtures").workspace_id
    gt = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="ground.jsonl",
    ).manifest.input_id
    pred = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=PRED,
        source_filename="predictions.jsonl",
    ).manifest.input_id
    service = RetrievalRunService(store)
    try:
        yield store, ws, service, root, gt, pred
    finally:
        service.stop()


def create_job(
    service: RetrievalRunService,
    workspace_id: str,
    gt: str,
    pred: str,
    *,
    name: str = "baseline",
) -> str:
    return service.create_and_enqueue(
        workspace_id,
        CreateRetrievalRun(
            run_name=name,
            ground_truth_input_id=gt,
            predictions_input_id=pred,
            top_k=1,
            system_name="fixture",
            dataset_name="test",
            dataset_version="v1",
        ),
    ).run_id


def wait_complete(store: WorkspaceStore, workspace_id: str, run_id: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        jobs = [j for j in store.list_job_records(workspace_id) if j.run_id == run_id]
        if jobs and jobs[-1].state == JobState.COMPLETE:
            return
        if jobs and jobs[-1].state in (JobState.FAILED, JobState.CANCELLED):
            pytest.fail(f"run did not complete: {jobs[-1].state}")
        time.sleep(0.01)
    pytest.fail("local evaluation did not complete")


def test_empty_workspace_has_no_baseline_and_does_not_create_state_file(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, _, root, _, _ = setup
    assert ComparisonService(store).get_baseline(ws) is None
    state = store.get_workspace_state(ws)
    assert state.schema_version == "workspace-state-v1"
    assert state.baseline is None
    assert not (root / "workspaces" / ws / "workspace-state.json").exists()


def test_completed_run_pins_verified_hash_and_survives_store_restart(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, service, root, gt, pred = setup
    run_id = create_job(service, ws, gt, pred)
    service.start()
    wait_complete(store, ws, run_id)
    _, provenance = store.get_run_artifacts(ws, run_id)

    state = ComparisonService(store).set_baseline(ws, run_id)
    assert state.baseline is not None
    assert state.baseline.run_id == run_id
    assert state.baseline.result_sha256 == provenance.result_sha256
    assert ComparisonService(WorkspaceStore(root)).get_baseline(ws) == state.baseline
    assert store.get_run_snapshot(ws, run_id).run_id == run_id
    assert list((root / "workspaces" / ws / "runs" / run_id).glob("*.tmp")) == []


def test_incomplete_run_or_foreign_run_cannot_be_pinned(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, service, _, gt, pred = setup
    unstarted = create_job(service, ws, gt, pred)
    with pytest.raises(WorkspaceStorageError):
        ComparisonService(store).set_baseline(ws, unstarted)
    assert ComparisonService(store).get_baseline(ws) is None

    foreign = store.create_workspace("Other").workspace_id
    with pytest.raises(WorkspaceStorageError):
        ComparisonService(store).set_baseline(foreign, unstarted)
    assert ComparisonService(store).get_baseline(foreign) is None


@pytest.mark.parametrize("terminal", [JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED])
def test_terminal_without_complete_evidence_is_not_pinnable(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
    terminal: JobState,
) -> None:
    store, ws, service, _, gt, pred = setup
    run_id = create_job(service, ws, gt, pred)
    job = next(item for item in store.list_job_records(ws) if item.run_id == run_id)
    if terminal == JobState.INTERRUPTED:
        job = store.update_job_record(
            ws, job.job_id, expected_revision=job.revision, next_state=JobState.VALIDATING
        )
    store.update_job_record(
        ws,
        job.job_id,
        expected_revision=job.revision,
        next_state=terminal,
        cancel_requested=terminal == JobState.CANCELLED,
        safe_error=(
            SafeJobError(code="TEST_STOP", message="test terminal state")
            if terminal != JobState.CANCELLED
            else None
        ),
    )
    with pytest.raises(WorkspaceStorageError):
        ComparisonService(store).set_baseline(ws, run_id)
    assert ComparisonService(store).get_baseline(ws) is None


def test_complete_status_without_artifacts_is_rejected(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, service, _, gt, pred = setup
    run_id = create_job(service, ws, gt, pred)
    job = next(item for item in store.list_job_records(ws) if item.run_id == run_id)
    for phase in (
        JobState.VALIDATING,
        JobState.EVALUATING,
        JobState.ANALYZING,
        JobState.WRITING_ARTIFACT,
        JobState.COMPLETE,
    ):
        job = store.update_job_record(
            ws, job.job_id, expected_revision=job.revision, next_state=phase
        )
    with pytest.raises(WorkspaceStorageError, match="incomplete"):
        ComparisonService(store).set_baseline(ws, run_id)
    assert ComparisonService(store).get_baseline(ws) is None


def test_tampered_completed_result_never_becomes_pinned_baseline(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, service, root, gt, pred = setup
    run_id = create_job(service, ws, gt, pred)
    service.start()
    wait_complete(store, ws, run_id)
    artifact = root / "workspaces" / ws / "runs" / run_id / "result.json"
    artifact.write_bytes(artifact.read_bytes() + b"\n")

    with pytest.raises(WorkspaceStorageError, match="checksum"):
        ComparisonService(store).set_baseline(ws, run_id)
    assert ComparisonService(store).get_baseline(ws) is None


def test_replacing_pointer_preserves_historical_run_artifacts(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, service, root, gt, pred = setup
    service.start()
    first_id = create_job(service, ws, gt, pred, name="first")
    wait_complete(store, ws, first_id)
    first = ComparisonService(store).set_baseline(ws, first_id).baseline
    first_run_files = {
        name: (root / "workspaces" / ws / "runs" / first_id / name).read_bytes()
        for name in ("config.json", "result.json", "provenance.json")
    }

    second_id = create_job(service, ws, gt, pred, name="second")
    wait_complete(store, ws, second_id)
    second = ComparisonService(store).set_baseline(ws, second_id).baseline
    assert first is not None and second is not None
    assert second.run_id != first.run_id
    assert store.get_workspace_state(ws).baseline == second
    for name, content in first_run_files.items():
        assert (root / "workspaces" / ws / "runs" / first_id / name).read_bytes() == content
    assert list(root.rglob("*.tmp")) == []


def test_invalid_state_document_and_symlink_are_rejected(
    setup: tuple[WorkspaceStore, str, RetrievalRunService, Path, str, str],
) -> None:
    store, ws, _, root, _, _ = setup
    path = root / "workspaces" / ws / "workspace-state.json"
    path.write_text('{"schema_version":"unknown"}', encoding="utf-8")
    with pytest.raises(WorkspaceStorageError):
        store.get_workspace_state(ws)

    path.unlink()
    target = root / "state-target.json"
    target.write_text('{"schema_version":"workspace-state-v1"}', encoding="utf-8")
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symlink privileges unavailable")
    with pytest.raises(WorkspaceStorageError):
        store.get_workspace_state(ws)
