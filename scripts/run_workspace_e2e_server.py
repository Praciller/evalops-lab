#!/usr/bin/env python3
"""Test-only server harness for Playwright E2E.

Receives a fixed test nonce and temp root via CLI arguments so that
Playwright tests can authenticate deterministically.

IMPORTANT: This is test infrastructure only. The production
`evalops workspace` command never accepts a fixed nonce argument.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Allow importing evalops from the repository root
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))


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
    args = parser.parse_args()

    # Use a temp root unless explicitly provided
    temp_dir_ctx = tempfile.TemporaryDirectory(prefix="evalops-e2e-")

    import uvicorn

    from evalops.workspace.api.app import create_workspace_app
    from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
    from evalops.workspace.storage import WorkspaceStore

    root = args.root or Path(temp_dir_ctx.name)
    origin = WorkspaceOrigin(host="127.0.0.1", port=args.port)

    class E2ETestSessionManager(BootstrapSessionManager):
        def consume_bootstrap_nonce(self, value: str) -> str:
            session_id = super().consume_bootstrap_nonce(value)
            self._bootstrap_nonce = args.nonce
            return session_id

    session_manager = E2ETestSessionManager(bootstrap_nonce=args.nonce)
    store = WorkspaceStore(root)

    # Point to the built Vite bundle in apps/workspace/dist
    static_dir = repo_root / "apps" / "workspace" / "dist"

    app = create_workspace_app(
        store,
        session_manager,
        origin,
        static_dir=static_dir if static_dir.is_dir() else None,
    )

    # Print the server URL for Playwright's webServer config
    print(f"E2E server ready at http://127.0.0.1:{args.port}", flush=True)
    print(
        f"Bootstrap URL: http://127.0.0.1:{args.port}/#bootstrap={args.nonce}",
        flush=True,
    )

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
