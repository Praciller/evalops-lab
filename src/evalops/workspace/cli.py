"""CLI adapter for the optional local Workspace runtime."""

from __future__ import annotations

import socket
import webbrowser
from pathlib import Path


def run_workspace_command(*, root: Path | None, port: int | None, open_browser: bool) -> int:
    """Start the local Workspace runtime.

    Runtime imports intentionally stay inside this function so core-only
    installations retain their existing import and CLI paths.
    """

    import uvicorn

    from evalops.workspace.api.app import create_workspace_app
    from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
    from evalops.workspace.storage import WorkspaceStore

    selected_port = _select_port(port)
    selected_root = root if root is not None else Path.home() / ".evalops"
    origin = WorkspaceOrigin(host="127.0.0.1", port=selected_port)
    session_manager = BootstrapSessionManager()
    store = WorkspaceStore(selected_root)
    static_dir = Path(__file__).resolve().parents[3] / "apps" / "workspace" / "dist"
    app = create_workspace_app(
        store,
        session_manager,
        origin,
        static_dir=static_dir if static_dir.is_dir() else None,
    )
    bootstrap_url = f"{origin.http_origin}/#bootstrap={session_manager.bootstrap_nonce}"
    if open_browser:
        webbrowser.open(bootstrap_url)
    else:
        print(bootstrap_url)
    uvicorn.run(app, host="127.0.0.1", port=selected_port)
    return 0


def _select_port(port: int | None) -> int:
    if port is not None:
        if not 1 <= port <= 65535:
            raise ValueError("workspace port must be between 1 and 65535")
        return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
