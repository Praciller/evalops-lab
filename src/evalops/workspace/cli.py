"""CLI adapter for the optional local Workspace runtime."""

from __future__ import annotations

from pathlib import Path


def run_workspace_command(*, root: Path | None, port: int | None, open_browser: bool) -> int:
    """Start the local Workspace runtime.

    Runtime imports intentionally stay inside this function so core-only
    installations retain their existing import and CLI paths.
    """

    import fastapi  # noqa: F401  # imported to provide a stable missing-extra boundary

    del root, port, open_browser
    raise RuntimeError("Workspace runtime is not initialized")
