#!/usr/bin/env python3
"""Stage deterministic Vite assets inside Python package data before wheel build.

Run after npm run build in apps/workspace. This never touches raw Workspace
inputs, export destinations, user profiles or GitHub Pages.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evalops.workspace.assets import (  # noqa: E402
    ASSET_MANIFEST,
    ASSET_SCHEMA,
    WorkspaceAssetsError,
    verify_staged_workspace_assets,
)

SOURCE = ROOT / "apps" / "workspace" / "dist"
DESTINATION = ROOT / "src" / "evalops" / "workspace" / "static"


def _validate_vite_entrypoint(entrypoint: bytes, files: set[str]) -> None:
    text = entrypoint.decode("utf-8")
    for ref in re.findall(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", text):
        if ref.startswith(("http:", "https:", "//")):
            raise WorkspaceAssetsError("external UI scripts or fonts are not allowed")
        if not ref.startswith("/assets/") or ref[1:] not in files:
            raise WorkspaceAssetsError("UI entrypoint references a missing or unsupported asset")


def stage_assets(source: Path, destination: Path) -> dict[str, str]:
    """Copy all Vite assets and write SHA-256 manifest with no machine metadata."""

    index = source / "index.html"
    assets = source / "assets"
    if (
        source.is_symlink()
        or not source.is_dir()
        or not index.is_file()
        or index.is_symlink()
        or not assets.is_dir()
        or assets.is_symlink()
    ):
        raise WorkspaceAssetsError("frontend build is missing index.html or assets")
    entries = [index, *sorted(assets.rglob("*"))]
    relative_files = [
        path.relative_to(source).as_posix()
        for path in entries
        if path.is_file()
    ]
    if len(relative_files) < 2 or len(relative_files) != len(set(relative_files)):
        raise WorkspaceAssetsError("frontend build contains no usable assets")
    for path in entries:
        if path.is_symlink():
            raise WorkspaceAssetsError("frontend build contains a symlink")
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            if (
                relative != "index.html"
                and (not relative.startswith("assets/") or relative.endswith(".map"))
            ):
                raise WorkspaceAssetsError("frontend build contains unsupported files")
            if relative.endswith(".css") and re.search(
                rb"(?i)(?:@import\s+|url\()\s*['\"]?https?://", path.read_bytes()
            ):
                raise WorkspaceAssetsError("external CSS resources are not allowed")
    _validate_vite_entrypoint(index.read_bytes(), set(relative_files))
    if destination.is_symlink():
        raise WorkspaceAssetsError("staging destination is a symlink")
    if destination.exists():
        # Never remove an unrelated directory or incomplete unmanaged content.
        verify_staged_workspace_assets(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".evalops-static-stage-", dir=destination.parent) as tmp:
        staging = Path(tmp) / "static"
        staging.mkdir()
        digest_map: dict[str, str] = {}
        for relative in sorted(relative_files):
            original = source / relative
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            digest_map[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        payload = {"schema_version": ASSET_SCHEMA, "files": digest_map}
        (staging / ASSET_MANIFEST).write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        verify_staged_workspace_assets(staging)
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    return digest_map


def main() -> int:
    try:
        files = stage_assets(SOURCE, DESTINATION)
    except (OSError, ValueError, WorkspaceAssetsError) as error:
        print("Workspace asset staging failed: " + str(error), file=sys.stderr)
        return 1
    print("Staged " + str(len(files)) + " verified files into Python package data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
