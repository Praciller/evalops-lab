"""Phase 6.2 Task 5: real deterministic runner and immutable local result provenance."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import pytest

from evalops.models.runs import EvaluationResult
from evalops.runners.retrieval import run_retrieval_evaluation
from evalops.workspace.application import runs
from evalops.workspace.application.runs import CreateRetrievalRun, RetrievalRunService
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl, register_referenced_jsonl
from evalops.workspace.jobs.models import JobState
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

GT = (
    b'{"query_id":"q1","relevant_document_ids":["doc1"]}\n'
    b'{"query_id":"q2","relevant_document_ids":["doc2"]}\n'
)
PRED = (
    b'{"query_id":"q1","retrieved_document_ids":["doc1","doc3"]}\n'
    b'{"query_id":"q2","retrieved_document_ids":["wrong","doc2"]}\n'
)


def _until(store: WorkspaceStore, ws: str, job_id: str, desired: JobState) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if store.get_job_record(ws, job_id).state == desired:
            return
        threading.Event().wait(0.01)
    pytest.fail(f"job did not reach {desired}")


@pytest.fixture
def prepared(tmp_path: Path) -> tuple[WorkspaceStore, str, str, str, Path]:
    root = tmp_path / "workspace"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("Private demo").workspace_id
    truth = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="truth.jsonl",
    ).manifest.input_id
    pred = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=PRED,
        source_filename="pred.jsonl",
    ).manifest.input_id
    return store, ws, truth, pred, root


def _request(truth: str, pred: str) -> CreateRetrievalRun:
    return CreateRetrievalRun(
        run_name="deterministic evaluation",
        ground_truth_input_id=truth,
        predictions_input_id=pred,
        top_k=2,
        system_name="fixture-bm25",
        dataset_name="synthetic-local",
        dataset_version="v1",
    )


def test_runner_parity_result_metrics_failures_and_hash_provenance(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, root = prepared
    called = []
    original = runs.run_retrieval_evaluation

    def spy(ground: object, predictions: object, config: object) -> EvaluationResult:
        called.append((ground, predictions, config))
        return original(ground, predictions, config)  # type: ignore[arg-type]

    monkeypatch.setattr(runs, "run_retrieval_evaluation", spy)
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, job.job_id, JobState.COMPLETE)
        assert len(called) == 1
        snapshot = store.get_run_snapshot(ws, job.run_id)
        direct = run_retrieval_evaluation(
            {"q1": ["doc1"], "q2": ["doc2"]},
            {"q1": ["doc1", "doc3"], "q2": ["wrong", "doc2"]},
            snapshot.config,
        )
        result, provenance = store.get_run_artifacts(ws, job.run_id)
        assert result.model_dump(mode="json") == direct.model_dump(mode="json")
        assert result.metrics == direct.metrics
        assert result.details["per_query"]
        assert provenance.run_id == job.run_id
        assert provenance.evaluator_versions == {"retrieval": "deterministic-v1"}
        assert provenance.ground_truth_content_sha256 == hashlib.sha256(GT).hexdigest()
        assert provenance.predictions_content_sha256 == hashlib.sha256(PRED).hexdigest()
        assert provenance.evalops_version
        result_path = root / "workspaces" / ws / "runs" / job.run_id / "result.json"
        provenance_path = result_path.parent / "provenance.json"
        assert provenance.result_sha256 == hashlib.sha256(result_path.read_bytes()).hexdigest()
        assert provenance_path.is_file()
        assert not list(root.rglob("*.tmp"))
        assert WorkspaceStore(root).get_run_artifacts(ws, job.run_id) == (result, provenance)
        assert store.get_job_record(ws, job.job_id).revision == 5
    finally:
        service.stop()


def test_referenced_input_mutation_fails_before_evaluator_runs(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, _, root = prepared
    source = tmp_path / "external-predictions.jsonl"
    source.write_bytes(PRED)
    pred = register_referenced_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        source=source,
    ).manifest.input_id
    called = []

    def fail_if_called(*_: object) -> EvaluationResult:
        called.append(True)
        raise RuntimeError("should not run")

    monkeypatch.setattr(runs, "run_retrieval_evaluation", fail_if_called)
    service = RetrievalRunService(store)
    job = service.create_and_enqueue(ws, _request(truth, pred))
    source.write_bytes(b'{"query_id":"q1","retrieved_document_ids":["changed"]}\n')
    service.start()
    try:
        _until(store, ws, job.job_id, JobState.FAILED)
        assert store.get_job_record(ws, job.job_id).safe_error.code == "INPUT_HASH_CHANGED"
        assert called == []
        assert list((root / "workspaces" / ws / "runs" / job.run_id).glob("result.json")) == []
    finally:
        service.stop()


def test_queued_cancel_skips_evaluator_and_artifacts(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, root = prepared
    seen = []
    monkeypatch.setattr(
        runs,
        "run_retrieval_evaluation",
        lambda *_: seen.append(1),
    )
    service = RetrievalRunService(store)
    job = service.create_and_enqueue(ws, _request(truth, pred))
    assert service.cancel_job(job.job_id).state == JobState.CANCELLED
    service.start()
    try:
        assert store.get_job_record(ws, job.job_id).state == JobState.CANCELLED
        assert seen == []
        with pytest.raises(WorkspaceStorageError):
            store.get_run_artifacts(ws, job.run_id)
        assert not list((root / "workspaces" / ws / "runs" / job.run_id).glob("result.json"))
    finally:
        service.stop()


def test_cancel_during_evaluation_before_artifact_promotion(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, root = prepared
    started, release = threading.Event(), threading.Event()
    original = runs.run_retrieval_evaluation

    def delayed(*args: object) -> EvaluationResult:
        started.set()
        assert release.wait(5)
        return original(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(runs, "run_retrieval_evaluation", delayed)
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        assert started.wait(5)
        requested = service.cancel_job(job.job_id)
        assert requested.cancel_requested
        release.set()
        _until(store, ws, job.job_id, JobState.CANCELLED)
        with pytest.raises(WorkspaceStorageError):
            store.get_run_artifacts(ws, job.run_id)
        run_folder = root / "workspaces" / ws / "runs" / job.run_id
        assert not (run_folder / "result.json").exists()
        assert not (run_folder / "provenance.json").exists()
    finally:
        release.set()
        service.stop()


def test_evaluator_error_is_sanitized_and_artifact_free(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, root = prepared

    def broken(*_: object) -> EvaluationResult:
        raise RuntimeError("PRIVATE: C:/secrets/credentials")

    monkeypatch.setattr(runs, "run_retrieval_evaluation", broken)
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, job.job_id, JobState.FAILED)
        error = store.get_job_record(ws, job.job_id).safe_error
        assert error is not None and error.code == "WORKER_ERROR"
        assert "PRIVATE" not in str(error)
        assert not list((root / "workspaces" / ws / "runs" / job.run_id).glob("result.json"))
    finally:
        service.stop()


def test_retry_creates_new_job_identity_and_preserves_history(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, _ = prepared
    original = runs.run_retrieval_evaluation
    invocations = 0

    def once_broken(*args: object) -> EvaluationResult:
        nonlocal invocations
        invocations += 1
        if invocations == 1:
            raise RuntimeError("injected failure")
        return original(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(runs, "run_retrieval_evaluation", once_broken)
    service = RetrievalRunService(store)
    service.start()
    try:
        first = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, first.job_id, JobState.FAILED)
        historic = store.get_job_record(ws, first.job_id)
        second = service.retry_job(ws, first.job_id)
        assert second.job_id != first.job_id
        assert second.run_id == first.run_id
        _until(store, ws, second.job_id, JobState.COMPLETE)
        assert store.get_job_record(ws, first.job_id) == historic
        with pytest.raises(ValueError):
            service.retry_job(ws, second.job_id)
    finally:
        service.stop()


def test_provenance_persistence_failure_rolls_back_provisional_result(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evalops.workspace import storage

    store, ws, truth, pred, root = prepared
    original = storage._atomic_create_json

    def refuse_provenance(path: Path, payload: object) -> None:
        if path.name == "provenance.json":
            raise OSError("injected provenance failure")
        original(path, payload)  # type: ignore[arg-type]

    monkeypatch.setattr(storage, "_atomic_create_json", refuse_provenance)
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, job.job_id, JobState.FAILED)
        result_dir = root / "workspaces" / ws / "runs" / job.run_id
        assert not (result_dir / "result.json").exists()
        assert not (result_dir / "provenance.json").exists()
        assert store.get_job_record(ws, job.job_id).safe_error is not None
    finally:
        service.stop()


def test_completed_run_files_refuse_overwrite_and_modified_result_hash(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = prepared
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, job.job_id, JobState.COMPLETE)
        result_dir = root / "workspaces" / ws / "runs" / job.run_id
        first_result = (result_dir / "result.json").read_bytes()
        first_prov = (result_dir / "provenance.json").read_bytes()
        with pytest.raises(WorkspaceStorageError):
            store.write_run_artifacts(ws, job.job_id, b"{}", None)
        assert (result_dir / "result.json").read_bytes() == first_result
        assert (result_dir / "provenance.json").read_bytes() == first_prov
        (result_dir / "result.json").write_bytes(b'{"tampered":true}\n')
        with pytest.raises(WorkspaceStorageError, match="checksum"):
            store.get_run_artifacts(ws, job.run_id)
    finally:
        service.stop()


def test_restart_interrupts_job_and_retry_creates_new_job(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = prepared
    service = RetrievalRunService(store)
    first = service.create_and_enqueue(ws, _request(truth, pred))
    store.update_job_record(ws, first.job_id, expected_revision=0, next_state=JobState.VALIDATING)
    restarted = RetrievalRunService(WorkspaceStore(root))
    restarted.start()
    try:
        interrupted = store.get_job_record(ws, first.job_id)
        assert interrupted.state == JobState.INTERRUPTED
        retry = restarted.retry_job(ws, first.job_id)
        _until(store, ws, retry.job_id, JobState.COMPLETE)
        assert store.get_job_record(ws, first.job_id) == interrupted
    finally:
        restarted.stop()


def test_running_cancel_after_validation_prevents_runner_call(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, _ = prepared
    reading, release = threading.Event(), threading.Event()
    original_read = store.read_input_bytes
    runner_called = []

    def gated_read(workspace_id: str, input_id: str) -> bytes:
        reading.set()
        assert release.wait(timeout=5)
        return original_read(workspace_id, input_id)

    def record_call(*_: object) -> EvaluationResult:
        runner_called.append(True)
        raise AssertionError("runner should not be called after cancel")

    service = RetrievalRunService(store)
    # Snapshot creation reads registered bytes, so schedule before gating.
    job = service.create_and_enqueue(ws, _request(truth, pred))
    monkeypatch.setattr(store, "read_input_bytes", gated_read)
    monkeypatch.setattr(runs, "run_retrieval_evaluation", record_call)
    service.start()
    try:
        assert reading.wait(timeout=5)
        assert service.cancel_job(job.job_id).cancel_requested is True
        release.set()
        _until(store, ws, job.job_id, JobState.CANCELLED)
        assert runner_called == []
    finally:
        release.set()
        service.stop()


def test_cancel_immediately_after_evaluator_returns_before_analysis(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, truth, pred, root = prepared
    service = RetrievalRunService(store)
    job = service.create_and_enqueue(ws, _request(truth, pred))
    original = runs.run_retrieval_evaluation
    invoked = []

    def cancel_after_calculation(*args: object) -> EvaluationResult:
        result = original(*args)  # type: ignore[arg-type]
        invoked.append(True)
        service.cancel_job(job.job_id)
        return result

    monkeypatch.setattr(runs, "run_retrieval_evaluation", cancel_after_calculation)
    service.start()
    try:
        _until(store, ws, job.job_id, JobState.CANCELLED)
        assert invoked == [True]
        folder = root / "workspaces" / ws / "runs" / job.run_id
        assert not (folder / "result.json").exists()
        assert not (folder / "provenance.json").exists()
    finally:
        service.stop()


def test_failed_atomic_result_creation_is_artifact_free(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evalops.workspace import storage

    store, ws, truth, pred, root = prepared
    original = storage._atomic_create_bytes

    def fail_for_result(path: Path, data: bytes) -> None:
        if path.name == "result.json":
            raise OSError("injected result write failure")
        original(path, data)

    monkeypatch.setattr(storage, "_atomic_create_bytes", fail_for_result)
    service = RetrievalRunService(store)
    job = service.create_and_enqueue(ws, _request(truth, pred))
    service.start()
    try:
        _until(store, ws, job.job_id, JobState.FAILED)
        folder = root / "workspaces" / ws / "runs" / job.run_id
        assert not (folder / "result.json").exists()
        assert not (folder / "provenance.json").exists()
        assert not list(folder.glob("*.tmp"))
    finally:
        service.stop()


def test_retry_cleans_orphan_result_from_interrupted_write_only(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = prepared
    first_service = RetrievalRunService(store)
    first = first_service.create_and_enqueue(ws, _request(truth, pred))
    revision = 0
    for phase in (
        JobState.VALIDATING,
        JobState.EVALUATING,
        JobState.ANALYZING,
        JobState.WRITING_ARTIFACT,
    ):
        current = store.update_job_record(
            ws, first.job_id, expected_revision=revision, next_state=phase
        )
        revision = current.revision
    folder = root / "workspaces" / ws / "runs" / first.run_id
    (folder / "result.json").write_bytes(b"orphan-from-crash")
    rebooted = RetrievalRunService(WorkspaceStore(root))
    rebooted.start()
    try:
        assert store.get_job_record(ws, first.job_id).state == JobState.INTERRUPTED
        replacement = rebooted.retry_job(ws, first.job_id)
        _until(store, ws, replacement.job_id, JobState.COMPLETE)
        assert replacement.job_id != first.job_id
        assert store.get_job_record(ws, first.job_id).state == JobState.INTERRUPTED
        stored_result, stored_provenance = store.get_run_artifacts(ws, first.run_id)
        assert stored_result.evaluation_type == "retrieval"
        assert (
            stored_provenance.result_sha256
            == hashlib.sha256((folder / "result.json").read_bytes()).hexdigest()
        )
    finally:
        rebooted.stop()


def test_provenance_metadata_must_match_immutable_snapshot(
    prepared: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    import json

    store, ws, truth, pred, root = prepared
    service = RetrievalRunService(store)
    service.start()
    try:
        job = service.create_and_enqueue(ws, _request(truth, pred))
        _until(store, ws, job.job_id, JobState.COMPLETE)
        path = root / "workspaces" / ws / "runs" / job.run_id / "provenance.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        assert original["evaluator_versions"] == {"retrieval": "deterministic-v1"}
        for mutation in (
            {"ground_truth_input_id": "input-" + "f" * 32},
            {"evaluator_versions": {"retrieval": "untrusted-v9"}},
            {"git_commit": "fake-commit"},
        ):
            path.write_text(json.dumps({**original, **mutation}), encoding="utf-8")
            with pytest.raises(WorkspaceStorageError, match="snapshot"):
                store.get_run_artifacts(ws, job.run_id)
        path.write_text(json.dumps(original), encoding="utf-8")
        assert store.get_run_artifacts(ws, job.run_id)[1].run_id == job.run_id
    finally:
        service.stop()
