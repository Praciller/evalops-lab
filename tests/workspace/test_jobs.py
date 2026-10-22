"""Persistent single-worker queue, cancellation, revisions and restart guarantees."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from evalops.workspace.application.runs import CreateRetrievalRun, create_retrieval_run
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.jobs.models import (
    InvalidJobTransitionError,
    JobRecord,
    JobState,
    SafeJobError,
)
from evalops.workspace.jobs.queue import SingleWorkerQueue
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

GT = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
PRED = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'


@pytest.fixture
def job_store(tmp_path: Path) -> tuple[WorkspaceStore, str, str, Path]:
    root = tmp_path / "private"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("Job tests").workspace_id
    ground = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_GROUND_TRUTH, data=GT, source_filename="ground.jsonl"
    ).manifest
    prediction = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_PREDICTIONS, data=PRED, source_filename="pred.jsonl"
    ).manifest
    run = create_retrieval_run(
        store,
        ws,
        CreateRetrievalRun(
            run_name="run",
            ground_truth_input_id=ground.input_id,
            predictions_input_id=prediction.input_id,
            top_k=1,
            system_name="fixture",
            dataset_name="test",
            dataset_version="v1",
        ),
    )
    return store, ws, run.run_id, root


def complete(job: JobRecord, queue: SingleWorkerQueue) -> None:
    for state in (
        JobState.EVALUATING,
        JobState.ANALYZING,
        JobState.WRITING_ARTIFACT,
        JobState.COMPLETE,
    ):
        queue.transition(job.workspace_id, job.job_id, state)


def wait_for_state(
    store: WorkspaceStore, workspace_id: str, job_id: str, expected: JobState
) -> JobRecord:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        record = store.get_job_record(workspace_id, job_id)
        if record.state == expected:
            return record
        threading.Event().wait(0.01)
    pytest.fail(f"job did not reach {expected}")


def test_versioned_job_is_durable_and_revision_monotonic(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    job = JobRecord.queued(ws, run_id)
    assert job.state == JobState.QUEUED and job.revision == 0
    store.save_job_record(job)
    assert WorkspaceStore(root).get_job_record(ws, job.job_id) == job
    started = store.update_job_record(
        ws, job.job_id, expected_revision=0, next_state=JobState.VALIDATING
    )
    assert started.state == JobState.VALIDATING and started.revision == 1
    evaluating = store.update_job_record(
        ws, job.job_id, expected_revision=1, next_state=JobState.EVALUATING
    )
    assert evaluating.revision == 2 and evaluating.updated_at >= started.updated_at
    with pytest.raises(InvalidJobTransitionError, match="stale"):
        store.update_job_record(ws, job.job_id, expected_revision=1, next_state=JobState.ANALYZING)
    assert WorkspaceStore(root).get_job_record(ws, job.job_id).revision == 2
    assert not list(root.rglob("*.tmp"))


def test_reject_illegal_transitions_and_missing_safe_failure_message(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, _ = job_store
    job = JobRecord.queued(ws, run_id)
    store.save_job_record(job)
    for invalid in (JobState.EVALUATING, JobState.COMPLETE, JobState.INTERRUPTED):
        with pytest.raises(InvalidJobTransitionError):
            store.update_job_record(ws, job.job_id, expected_revision=0, next_state=invalid)
    with pytest.raises(InvalidJobTransitionError, match="safe error"):
        store.update_job_record(ws, job.job_id, expected_revision=0, next_state=JobState.FAILED)
    with pytest.raises(InvalidJobTransitionError, match="no-op"):
        store.update_job_record(ws, job.job_id, expected_revision=0)
    assert store.get_job_record(ws, job.job_id).revision == 0
    cancelled = store.update_job_record(
        ws,
        job.job_id,
        expected_revision=0,
        next_state=JobState.CANCELLED,
        cancel_requested=True,
    )
    with pytest.raises(InvalidJobTransitionError, match="terminal"):
        store.update_job_record(
            ws,
            job.job_id,
            expected_revision=cancelled.revision,
            next_state=JobState.VALIDATING,
        )


def test_persisted_worker_failure_uses_safe_code_without_exception_text(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store

    def failing_executor(job: JobRecord, _: SingleWorkerQueue) -> None:
        raise RuntimeError("SECRET: C:/private/local/path")

    worker = SingleWorkerQueue(store, failing_executor)
    worker.start()
    try:
        job = JobRecord.queued(ws, run_id)
        worker.enqueue(job)
        failed = wait_for_state(store, ws, job.job_id, JobState.FAILED)
        assert failed.safe_error == SafeJobError(
            code="WORKER_ERROR", message="job execution failed"
        )
        assert "SECRET" not in str(failed.model_dump())
        assert (
            "private/local"
            not in (root / "workspaces" / ws / "jobs" / job.job_id / "job.json").read_text()
        )
    finally:
        worker.stop()


def test_single_worker_runs_jobs_sequentially_and_keeps_history(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, _ = job_store
    entered = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    sequence: list[str] = []

    def executor(job: JobRecord, worker: SingleWorkerQueue) -> None:
        sequence.append(job.job_id)
        if len(sequence) == 1:
            entered.set()
            assert release.wait(timeout=5)
        else:
            second_started.set()
        complete(job, worker)

    worker = SingleWorkerQueue(store, executor)
    worker.start()
    first = JobRecord.queued(ws, run_id)
    second = JobRecord.queued(ws, run_id)
    try:
        worker.enqueue(first)
        assert entered.wait(5)
        worker.enqueue(second)
        assert not second_started.is_set()
        assert store.get_job_record(ws, second.job_id).state == JobState.QUEUED
        release.set()
        assert second_started.wait(5)
        assert wait_for_state(store, ws, first.job_id, JobState.COMPLETE).revision == 5
        assert wait_for_state(store, ws, second.job_id, JobState.COMPLETE).revision == 5
        assert sequence == [first.job_id, second.job_id]
        assert len(store.list_job_records(ws)) == 2
    finally:
        release.set()
        worker.stop()


def test_queued_cancel_skips_job_even_when_reference_remains_in_memory(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, _ = job_store
    entered = threading.Event()
    release = threading.Event()
    executed: list[str] = []

    def executor(job: JobRecord, worker: SingleWorkerQueue) -> None:
        executed.append(job.job_id)
        entered.set()
        assert release.wait(timeout=5)
        complete(job, worker)

    worker = SingleWorkerQueue(store, executor)
    worker.start()
    first, cancelled = JobRecord.queued(ws, run_id), JobRecord.queued(ws, run_id)
    try:
        worker.enqueue(first)
        assert entered.wait(5)
        worker.enqueue(cancelled)
        stopped = worker.request_cancel(cancelled.job_id)
        assert stopped.state == JobState.CANCELLED
        assert stopped.cancel_requested is True
        assert worker.request_cancel(cancelled.job_id) == stopped
        release.set()
        assert wait_for_state(store, ws, first.job_id, JobState.COMPLETE)
        worker.stop()
        assert executed == [first.job_id]
        assert store.get_job_record(ws, cancelled.job_id) == stopped
    finally:
        release.set()
        worker.stop()


def test_running_cancel_is_cooperative_and_terminal_idempotent(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, _ = job_store
    started, release = threading.Event(), threading.Event()

    def executor(job: JobRecord, worker: SingleWorkerQueue) -> None:
        started.set()
        assert release.wait(5)
        current = worker.get(job.workspace_id, job.job_id)
        assert current.cancel_requested is True
        worker.transition(job.workspace_id, job.job_id, JobState.CANCELLED)

    worker = SingleWorkerQueue(store, executor)
    worker.start()
    job = JobRecord.queued(ws, run_id)
    try:
        worker.enqueue(job)
        assert started.wait(5)
        requested = worker.request_cancel(job.job_id)
        assert requested.state == JobState.VALIDATING
        assert requested.cancel_requested and requested.revision == 2
        assert worker.request_cancel(job.job_id) == requested
        release.set()
        ended = wait_for_state(store, ws, job.job_id, JobState.CANCELLED)
        assert ended.revision == 3
        assert worker.request_cancel(job.job_id) == ended
    finally:
        release.set()
        worker.stop()


def test_recover_queued_and_interrupt_transient_but_preserve_terminals(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    queued, active, cancelled, completed = [JobRecord.queued(ws, run_id) for _ in range(4)]
    for record in (queued, active, cancelled, completed):
        store.save_job_record(record)
    store.update_job_record(ws, active.job_id, expected_revision=0, next_state=JobState.VALIDATING)
    store.update_job_record(
        ws,
        cancelled.job_id,
        expected_revision=0,
        next_state=JobState.CANCELLED,
        cancel_requested=True,
    )
    revision = 0
    for phase in (
        JobState.VALIDATING,
        JobState.EVALUATING,
        JobState.ANALYZING,
        JobState.WRITING_ARTIFACT,
        JobState.COMPLETE,
    ):
        updated = store.update_job_record(
            ws, completed.job_id, expected_revision=revision, next_state=phase
        )
        revision = updated.revision
    ran: list[str] = []

    def executor(job: JobRecord, worker: SingleWorkerQueue) -> None:
        ran.append(job.job_id)
        complete(job, worker)

    reloaded = WorkspaceStore(root)
    worker = SingleWorkerQueue(reloaded, executor)
    worker.recover()
    interrupted = reloaded.get_job_record(ws, active.job_id)
    assert interrupted.state == JobState.INTERRUPTED and interrupted.revision == 2
    assert interrupted.safe_error is not None
    assert reloaded.get_job_record(ws, cancelled.job_id).state == JobState.CANCELLED
    assert reloaded.get_job_record(ws, completed.job_id).state == JobState.COMPLETE
    worker.start()
    try:
        assert wait_for_state(reloaded, ws, queued.job_id, JobState.COMPLETE)
        assert ran == [queued.job_id]
        assert reloaded.get_job_record(ws, active.job_id) == interrupted
    finally:
        worker.stop()


def test_stop_does_not_discard_queued_jobs_from_disk(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    worker = SingleWorkerQueue(store, complete)
    job = JobRecord.queued(ws, run_id)
    worker.enqueue(job)
    worker.stop()
    assert store.get_job_record(ws, job.job_id).state == JobState.QUEUED
    recovered = SingleWorkerQueue(WorkspaceStore(root), complete)
    recovered.start()
    try:
        assert wait_for_state(store, ws, job.job_id, JobState.COMPLETE)
    finally:
        recovered.stop()


def test_job_record_validation_and_cross_workspace_access_fail_closed(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    job = JobRecord.queued(ws, run_id)
    store.save_job_record(job)
    other = store.create_workspace("Other").workspace_id
    with pytest.raises(WorkspaceStorageError):
        store.get_job_record(other, job.job_id)
    with pytest.raises(WorkspaceStorageError):
        store.get_job_record(ws, "../parent")
    with pytest.raises(WorkspaceStorageError):
        store.save_job_record(job)
    with pytest.raises(ValidationError):
        JobRecord.queued("ws-not-canonical", run_id)
    path = root / "workspaces" / ws / "jobs" / job.job_id / "job.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "workspace-job-v999"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkspaceStorageError):
        store.get_job_record(ws, job.job_id)
    with pytest.raises(WorkspaceStorageError):
        SingleWorkerQueue(WorkspaceStore(root), complete).start()


def test_restart_new_job_not_reusing_interrupted_identity(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    original = JobRecord.queued(ws, run_id)
    store.save_job_record(original)
    store.update_job_record(
        ws, original.job_id, expected_revision=0, next_state=JobState.VALIDATING
    )
    restarted = SingleWorkerQueue(WorkspaceStore(root), complete)
    restarted.start()
    try:
        assert store.get_job_record(ws, original.job_id).state == JobState.INTERRUPTED
        replacement = JobRecord.queued(ws, run_id)
        restarted.enqueue(replacement)
        assert wait_for_state(store, ws, replacement.job_id, JobState.COMPLETE)
        assert replacement.job_id != original.job_id
    finally:
        restarted.stop()


@pytest.mark.parametrize(
    "transient",
    [JobState.VALIDATING, JobState.EVALUATING, JobState.ANALYZING, JobState.WRITING_ARTIFACT],
)
def test_recovery_interrupts_each_transient_phase_once(
    job_store: tuple[WorkspaceStore, str, str, Path], transient: JobState
) -> None:
    store, ws, run_id, root = job_store
    job = JobRecord.queued(ws, run_id)
    store.save_job_record(job)
    revision = 0
    for phase in (
        JobState.VALIDATING,
        JobState.EVALUATING,
        JobState.ANALYZING,
        JobState.WRITING_ARTIFACT,
    ):
        record = store.update_job_record(
            ws, job.job_id, expected_revision=revision, next_state=phase
        )
        revision = record.revision
        if phase == transient:
            break
    worker = SingleWorkerQueue(WorkspaceStore(root), complete)
    worker.recover()
    interrupted = store.get_job_record(ws, job.job_id)
    assert interrupted.state == JobState.INTERRUPTED
    assert interrupted.revision == revision + 1
    assert interrupted.safe_error is not None
    assert interrupted.safe_error.code == "WORKER_RESTART"
    worker.recover()
    assert store.get_job_record(ws, job.job_id) == interrupted


def test_concurrent_revision_writes_have_exactly_one_winner(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, _ = job_store
    job = JobRecord.queued(ws, run_id)
    store.save_job_record(job)
    gate = threading.Barrier(3)
    results: list[JobState] = []
    failures: list[type[Exception]] = []

    def race(target: JobState) -> None:
        gate.wait(timeout=5)
        try:
            updated = store.update_job_record(
                ws, job.job_id, expected_revision=0, next_state=target
            )
            results.append(updated.state)
        except InvalidJobTransitionError as error:
            failures.append(type(error))

    threads = [
        threading.Thread(target=race, args=(JobState.VALIDATING,)),
        threading.Thread(target=race, args=(JobState.CANCELLED,)),
    ]
    for thread in threads:
        thread.start()
    gate.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(results) == len(failures) == 1
    assert failures == [InvalidJobTransitionError]
    persisted = store.get_job_record(ws, job.job_id)
    assert persisted.revision == 1
    assert persisted.state == results[0]


def test_failed_job_replace_preserves_previous_persisted_revision(
    job_store: tuple[WorkspaceStore, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evalops.workspace import storage

    store, ws, run_id, root = job_store
    job = JobRecord.queued(ws, run_id)
    store.save_job_record(job)
    path = root / "workspaces" / ws / "jobs" / job.job_id / "job.json"
    original = path.read_bytes()

    def fail_replace(_: object, __: object) -> None:
        raise OSError("injected atomic replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected atomic replace failure"):
        store.update_job_record(ws, job.job_id, expected_revision=0, next_state=JobState.VALIDATING)
    assert path.read_bytes() == original
    assert not list(root.rglob("*.tmp"))


def test_stop_waits_for_running_job_and_preserves_pending_for_recovery(
    job_store: tuple[WorkspaceStore, str, str, Path],
) -> None:
    store, ws, run_id, root = job_store
    entered = threading.Event()
    release = threading.Event()
    seen: list[str] = []

    def executor(job: JobRecord, worker: SingleWorkerQueue) -> None:
        seen.append(job.job_id)
        entered.set()
        assert release.wait(timeout=5)
        complete(job, worker)

    worker = SingleWorkerQueue(store, executor)
    worker.start()
    first, later = JobRecord.queued(ws, run_id), JobRecord.queued(ws, run_id)
    worker.enqueue(first)
    assert entered.wait(5)
    worker.enqueue(later)
    stop_done = threading.Event()

    def close() -> None:
        worker.stop()
        stop_done.set()

    closing = threading.Thread(target=close)
    closing.start()
    # Test-only rendezvous: shutdown must be requested before releasing job 1.
    # Without this, job 2 could legitimately run before stop() acquires the lock.
    assert worker._stop_requested.wait(timeout=5)
    assert not stop_done.is_set()
    release.set()
    closing.join(timeout=5)
    assert stop_done.is_set()
    assert wait_for_state(store, ws, first.job_id, JobState.COMPLETE)
    assert store.get_job_record(ws, later.job_id).state == JobState.QUEUED
    assert seen == [first.job_id]
    restarted = SingleWorkerQueue(WorkspaceStore(root), complete)
    restarted.start()
    try:
        assert wait_for_state(store, ws, later.job_id, JobState.COMPLETE)
    finally:
        restarted.stop()
