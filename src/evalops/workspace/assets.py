"""Verified front-end assets in an installed wheel or an explicit source checkout."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

ASSET_MANIFEST = "assets-manifest.json"
ASSET_SCHEMA = "workspace-static-assets-v1"


class WorkspaceAssetsError(RuntimeError):
    """An incomplete or tampered UI build must never be silently served."""


def verify_staged_workspace_assets(root: Path) -> dict[str, str]:
    """Verify that every staged file is listed with a matching content digest."""

    if not root.is_dir() or root.is_symlink():
        raise WorkspaceAssetsError("workspace UI package directory is unavailable")
    manifest = root / ASSET_MANIFEST
    if not manifest.is_file() or manifest.is_symlink():
        raise WorkspaceAssetsError("workspace UI package manifest is unavailable")
    try:
        payload: Any = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkspaceAssetsError("workspace UI package manifest is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != ASSET_SCHEMA:
        raise WorkspaceAssetsError("workspace UI package manifest schema is invalid")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise WorkspaceAssetsError("workspace UI package file listing is invalid")
    if "index.html" not in files or not any(name.startswith("assets/") for name in files):
        raise WorkspaceAssetsError("workspace UI package is incomplete")

    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise WorkspaceAssetsError("workspace UI package contains a symlink")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name != ASSET_MANIFEST:
                actual.add(name)
    if actual != set(files):
        raise WorkspaceAssetsError("workspace UI package files do not match manifest")

    validated: dict[str, str] = {}
    for name, expected in sorted(files.items()):
        if (
            not isinstance(name, str)
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
            or name.startswith("/")
            or "\\" in name
            or ".." in Path(name).parts
            or name not in actual
        ):
            raise WorkspaceAssetsError("workspace UI package contains an unsafe manifest entry")
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if digest != expected:
            raise WorkspaceAssetsError("workspace UI package checksum mismatch")
        validated[name] = expected
    return validated


def resolve_workspace_static_dir(
    *, package_dir: Path | None = None, checkout_root: Path | None = None
) -> Path:
    """Prefer a checksum-verified packaged UI; use dist only in source checkout."""

    if package_dir is None:
        package_dir = Path(str(resources.files("evalops.workspace").joinpath("static")))
    if package_dir.exists() or package_dir.is_symlink():
        verify_staged_workspace_assets(package_dir)
        return package_dir

    if checkout_root is None:
        checkout_root = Path(__file__).resolve().parents[3]
    fallback = checkout_root / "apps" / "workspace" / "dist"
    if (
        (checkout_root / "pyproject.toml").is_file()
        and fallback.is_dir()
        and not fallback.is_symlink()
        and (fallback / "index.html").is_file()
        and (fallback / "assets").is_dir()
        and not (fallback / "assets").is_symlink()
    ):
        return fallback
    raise WorkspaceAssetsError(
        "Workspace UI assets unavailable; build apps/workspace and stage the package assets"
    )
