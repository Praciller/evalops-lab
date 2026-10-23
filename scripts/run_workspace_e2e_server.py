#!/usr/bin/env python3
"""Test-only server harness for Playwright E2E.

Receives a fixed test nonce and temp root via CLI arguments so that
Playwright tests can authenticate deterministically.

Supports test-only supervisor process control to simulate a real
server-process restart with the same root directory.

IMPORTANT: This is test infrastructure only. The production
`evalops workspace` command never accepts a fixed nonce argument
or test restart controls.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# Allow importing evalops from the repository root
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

RESTART_EXIT_CODE = 42


def _run_worker(port: int, nonce: str, root: Path) -> None:
    import uvicorn

    from evalops.workspace.api.app import create_workspace_app
    from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
    from evalops.workspace.storage import WorkspaceStore

    origin = WorkspaceOrigin(host="127.0.0.1", port=port)

    class E2ETestSessionManager(BootstrapSessionManager):
        def consume_bootstrap_nonce(self, value: str) -> str:
            session_id = super().consume_bootstrap_nonce(value)
            self._bootstrap_nonce = nonce
            return session_id

    session_manager = E2ETestSessionManager(bootstrap_nonce=nonce)
    store = WorkspaceStore(root)

    # Test-only deterministic gate at the worker boundary. Never loaded in production.
    from evalops.workspace.application.runs import (
        CreateRetrievalRun,
        RetrievalRunService,
        create_retrieval_run,
    )
    from evalops.workspace.ingestion.models import InputKind
    from evalops.workspace.jobs.models import JobRecord, JobState

    gate_enabled = threading.Event()
    gate_entered = threading.Event()
    gate_release = threading.Event()
    original_execute = RetrievalRunService.execute_job

    def gated_execute(self: RetrievalRunService, workspace_id: str, job_id: str) -> None:
        if gate_enabled.is_set():
            gate_enabled.clear()
            gate_entered.set()
            if not gate_release.wait(timeout=20):
                raise RuntimeError("test gate release timed out")
        original_execute(self, workspace_id, job_id)

    RetrievalRunService.execute_job = gated_execute

    # Point to the built Vite bundle in apps/workspace/dist
    static_dir = repo_root / "apps" / "workspace" / "dist"

    app = create_workspace_app(
        store,
        session_manager,
        origin,
        static_dir=static_dir if static_dir.is_dir() else None,
    )

    # Test-only endpoints for Playwright E2E process restart verification
    @app.get("/__test__/pid")
    async def get_test_pid() -> dict[str, int]:
        return {"pid": os.getpid()}

    @app.post("/__test__/restart")
    async def post_test_restart() -> dict[str, object]:
        current_pid = os.getpid()
        loop = asyncio.get_running_loop()
        loop.call_later(0.1, lambda: os._exit(RESTART_EXIT_CODE))
        return {"status": "restarting", "pid": current_pid}

    @app.post("/__test__/gate/enable")
    async def enable_gate() -> dict[str, bool]:
        gate_entered.clear()
        gate_release.clear()
        gate_enabled.set()
        return {"enabled": True}

    @app.get("/__test__/gate/status")
    async def gate_status() -> dict[str, bool]:
        return {"entered": gate_entered.is_set()}

    @app.post("/__test__/gate/release")
    async def release_gate() -> dict[str, bool]:
        gate_release.set()
        return {"released": True}

    @app.post("/__test__/fixture/reference")
    async def create_reference() -> dict[str, str]:
        target = root / "test-synthetic" / "predictions.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"query_id":"q1","retrieved_document_ids":["d1"]}\n', encoding="utf-8")
        return {"path": str(target.resolve())}

    @app.post("/__test__/fixture/mutate")
    async def mutate_reference() -> dict[str, bool]:
        target = root / "test-synthetic" / "predictions.jsonl"
        if not target.is_file():
            return {"mutated": False}
        target.write_text(
            '{"query_id":"q1","retrieved_document_ids":["CHANGED"]}\n', encoding="utf-8"
        )
        return {"mutated": True}

    def latest_test_workspace_id() -> str:
        # Test-only: derive identity from owned disk state, never HTTP parameters.
        workspaces = store.list_workspaces()
        if not workspaces:
            raise RuntimeError("E2E fixture requires a registered workspace")
        return max(workspaces, key=lambda item: item.created_at).workspace_id

    @app.post("/__test__/jobs/seed-transient")
    async def seed_transient() -> dict[str, str]:
        workspace_id = latest_test_workspace_id()
        inputs = store.list_inputs(workspace_id)
        ground = next(item for item in inputs if item.kind == InputKind.RETRIEVAL_GROUND_TRUTH)
        predictions = next(item for item in inputs if item.kind == InputKind.RETRIEVAL_PREDICTIONS)
        snapshot = create_retrieval_run(
            store,
            workspace_id,
            CreateRetrievalRun(
                run_name="Synthetic interrupted run",
                ground_truth_input_id=ground.input_id,
                predictions_input_id=predictions.input_id,
                top_k=2,
                system_name="synthetic-e2e",
                dataset_name="synthetic-fixture",
                dataset_version="v1",
            ),
        )
        job = JobRecord.queued(workspace_id, snapshot.run_id)
        store.save_job_record(job)
        store.update_job_record(
            workspace_id,
            job.job_id,
            expected_revision=0,
            next_state=JobState.VALIDATING,
        )
        return {"workspace_id": workspace_id, "job_id": job.job_id, "run_id": snapshot.run_id}

    @app.get("/__test__/artifacts/status")
    async def artifact_status() -> dict[str, str | bool]:
        # Never accept path identifiers from unauthenticated fixture requests.
        workspace_id = latest_test_workspace_id()
        snapshots = store.list_run_snapshots(workspace_id)
        if not snapshots:
            raise RuntimeError("E2E fixture requires a run")
        run_id = max(snapshots, key=lambda run: run.created_at).run_id
        directory = store._run_config_path(workspace_id, run_id).parent
        return {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "result": (directory / "result.json").exists(),
            "provenance": (directory / "provenance.json").exists(),
        }

    # Reorder routes so test endpoints match before the catch-all SPA route /{path:path}
    test_routes = [r for r in app.router.routes if getattr(r, "path", "").startswith("/__test__")]
    other_routes = [
        r for r in app.router.routes if not getattr(r, "path", "").startswith("/__test__")
    ]
    app.router.routes = test_routes + other_routes

    print(f"E2E server ready at http://127.0.0.1:{port} (PID: {os.getpid()})", flush=True)
    print(f"Bootstrap URL: http://127.0.0.1:{port}/#bootstrap={nonce}", flush=True)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _run_supervisor(port: int, nonce: str, root: Path) -> None:
    current_child: subprocess.Popen[bytes] | None = None

    def cleanup() -> None:
        nonlocal current_child
        if current_child and current_child.poll() is None:
            try:
                current_child.terminate()
                current_child.wait(timeout=2)
            except Exception:
                try:
                    current_child.kill()
                except Exception:
                    pass

    atexit.register(cleanup)

    def handle_signal(signum: int, frame: object) -> None:
        cleanup()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    except (ValueError, AttributeError):
        pass

    script_path = str(Path(__file__).resolve())
    cmd = [
        sys.executable,
        script_path,
        "--worker",
        "--port",
        str(port),
        "--nonce",
        nonce,
        "--root",
        str(root),
    ]

    while True:
        current_child = subprocess.Popen(cmd)
        try:
            exit_code = current_child.wait()
        except KeyboardInterrupt:
            cleanup()
            break

        if exit_code == RESTART_EXIT_CODE:
            # Brief pause for the OS to release the socket before starting new worker
            time.sleep(0.3)
            continue

        sys.exit(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2E test server for Playwright workspace smoke tests."
    )
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--nonce",
        required=True,
        help="Fixed bootstrap nonce for deterministic E2E tests only.",
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Internal flag: run as worker process rather than supervisor.",
    )
    args = parser.parse_args()

    # If already in worker mode, run directly
    if args.worker:
        assert args.root is not None, "Worker requires explicit --root"
        _run_worker(args.port, args.nonce, args.root)
        return

    # Supervisor mode: ensure a stable temp directory across restarts
    if args.root is not None:
        _run_supervisor(args.port, args.nonce, args.root)
    else:
        with tempfile.TemporaryDirectory(prefix="evalops-e2e-") as temp_dir:
            _run_supervisor(args.port, args.nonce, Path(temp_dir))


if __name__ == "__main__":
    main()
