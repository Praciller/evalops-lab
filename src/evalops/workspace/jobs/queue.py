"""Durable single-worker job scheduling; persisted JSON is authoritative."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from evalops.workspace.jobs.models import (
    TERMINAL_STATES,
    InvalidJobTransitionError,
    JobRecord,
    JobState,
    SafeJobError,
)
from evalops.workspace.storage import WorkspaceStore

JobExecutor = Callable[[JobRecord, "SingleWorkerQueue"], None]


class SingleWorkerQueue:
    """One local worker; queued references survive process restarts on disk.

    Callbacks implement evaluation phases (Task 5). This scheduler never executes
    arbitrary subprocesses and never stores input payloads in its in-memory queue.
    """

    def __init__(self, store: WorkspaceStore, executor: JobExecutor) -> None:
        self._store = store
        self._executor = executor
        self._pending: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._pending_ids: set[tuple[str, str]] = set()
        self._lock = threading.RLock()
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    def _schedule(self, workspace_id: str, job_id: str) -> None:
        with self._lock:
            identity = (workspace_id, job_id)
            if identity not in self._pending_ids:
                self._pending_ids.add(identity)
                self._pending.put(identity)

    def enqueue(self, job: JobRecord) -> None:
        """Create durable QUEUED state before advertising it to the worker."""
        with self._lock:
            if self._stop_requested.is_set():
                raise RuntimeError("job queue is stopping")
            self._store.save_job_record(job)
            if self._thread is not None:
                self._schedule(job.workspace_id, job.job_id)

    def recover(self) -> None:
        """Rehydrate pending jobs; interrupt in-flight work instead of replaying it."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("cannot recover while worker is running")
            for workspace in self._store.list_workspaces():
                for job in self._store.list_job_records(workspace.workspace_id):
                    if job.state == JobState.QUEUED:
                        self._schedule(job.workspace_id, job.job_id)
                    elif job.state not in TERMINAL_STATES:
                        self._store.update_job_record(
                            job.workspace_id,
                            job.job_id,
                            expected_revision=job.revision,
                            next_state=JobState.INTERRUPTED,
                            safe_error=SafeJobError(
                                code="WORKER_RESTART", message="job interrupted by restart"
                            ),
                        )

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_requested.clear()
            self._pending = queue.Queue()
            self._pending_ids.clear()
            self.recover()
            worker = threading.Thread(
                target=self._worker_loop, name="evalops-workspace-job-worker", daemon=True
            )
            self._thread = worker
            worker.start()

    def stop(self, timeout: float | None = None) -> None:
        """Cooperative shutdown; synchronous callback cannot be force-interrupted."""
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_requested.set()
            self._pending.put(None)
        if threading.current_thread() is thread:
            raise RuntimeError("worker cannot join itself")
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise RuntimeError("worker is still processing a job")
        with self._lock:
            self._thread = None

    def request_cancel(self, job_id: str) -> JobRecord:
        """Queued jobs cancel now; running jobs set a durable cooperative flag."""
        for _ in range(8):
            job = self._store.find_job_record(job_id)
            if job.state in TERMINAL_STATES or job.cancel_requested:
                return job
            try:
                return self._store.update_job_record(
                    job.workspace_id,
                    job.job_id,
                    expected_revision=job.revision,
                    next_state=JobState.CANCELLED if job.state == JobState.QUEUED else None,
                    cancel_requested=True,
                )
            except InvalidJobTransitionError:
                continue
        raise InvalidJobTransitionError("job cancellation could not be serialized")

    def transition(
        self,
        workspace_id: str,
        job_id: str,
        next_state: JobState,
        *,
        safe_error: SafeJobError | None = None,
    ) -> JobRecord:
        """Explicit transition for Task 5's executor at deterministic boundaries."""
        record = self._store.get_job_record(workspace_id, job_id)
        return self._store.update_job_record(
            workspace_id,
            job_id,
            expected_revision=record.revision,
            next_state=next_state,
            safe_error=safe_error,
        )

    def get(self, workspace_id: str, job_id: str) -> JobRecord:
        return self._store.get_job_record(workspace_id, job_id)

    def _worker_loop(self) -> None:
        while True:
            item = self._pending.get()
            try:
                if item is None:
                    return
                workspace_id, job_id = item
                with self._lock:
                    self._pending_ids.discard(item)
                if self._stop_requested.is_set():
                    continue  # Disk still says QUEUED; start() recovers it later.
                current = self._store.get_job_record(workspace_id, job_id)
                if current.state != JobState.QUEUED:
                    continue  # Cancelled in memory queue or already terminal.
                try:
                    current = self._store.update_job_record(
                        workspace_id,
                        job_id,
                        expected_revision=current.revision,
                        next_state=JobState.VALIDATING,
                    )
                except InvalidJobTransitionError:
                    continue  # A concurrent cancel/transition won the state race.
                # A cancel may win immediately after QUEUED -> VALIDATING;
                # skip executor work at this safe boundary.
                latest = self._store.get_job_record(workspace_id, job_id)
                if latest.cancel_requested:
                    self._finish_uncompleted(workspace_id, job_id)
                    continue
                try:
                    self._executor(latest, self)
                except Exception:
                    # Never persist exception text, private file paths or traceback.
                    self._finish_uncompleted(
                        workspace_id,
                        job_id,
                        error=SafeJobError(code="WORKER_ERROR", message="job execution failed"),
                    )
                else:
                    self._finish_uncompleted(workspace_id, job_id)
            finally:
                self._pending.task_done()

    def _finish_uncompleted(
        self, workspace_id: str, job_id: str, *, error: SafeJobError | None = None
    ) -> None:
        for _ in range(8):
            job = self._store.get_job_record(workspace_id, job_id)
            if job.state in TERMINAL_STATES:
                return
            target = JobState.CANCELLED if job.cancel_requested else JobState.FAILED
            safe = (
                None
                if job.cancel_requested
                else error
                or SafeJobError(
                    code="INCOMPLETE_EXECUTION", message="job did not reach a terminal state"
                )
            )
            try:
                self._store.update_job_record(
                    workspace_id,
                    job_id,
                    expected_revision=job.revision,
                    next_state=target,
                    safe_error=safe,
                )
                return
            except InvalidJobTransitionError:
                continue  # Cancellation may have advanced the revision concurrently.
        raise InvalidJobTransitionError("job finalization could not be serialized")
