"""Deterministic frontend staging and fail-closed installed-resource selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evalops.workspace.assets import (
    ASSET_MANIFEST,
    WorkspaceAssetsError,
    resolve_workspace_static_dir,
    verify_staged_workspace_assets,
)
from evalops.workspace.cli import run_workspace_command
from scripts.stage_workspace_assets import stage_assets


def _vite_fixture(tmp_path: Path) -> Path:
    dist = tmp_path / "fake-checkout" / "apps" / "workspace" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="/assets/app.css"></head>'
        '<body><script type="module" src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (assets / "app.css").write_text("body { margin: 0 }", encoding="utf-8")
    (assets / "app.js").write_text("console.log('safe UI')", encoding="utf-8")
    return dist


def test_stage_manifest_exact_hash_and_repeated_determinism(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    target = tmp_path / "package" / "static"
    first = stage_assets(dist, target)
    assert set(first) == {"index.html", "assets/app.css", "assets/app.js"}
    assert verify_staged_workspace_assets(target) == first
    manifest = (target / ASSET_MANIFEST).read_bytes()
    assert manifest.endswith(b"\n")
    assert b"fake-checkout" not in manifest
    for name, digest in first.items():
        assert digest == hashlib.sha256((target / name).read_bytes()).hexdigest()
    second = stage_assets(dist, target)
    assert second == first
    assert (target / ASSET_MANIFEST).read_bytes() == manifest
    assert list(target.parent.glob(".evalops-static-stage-*")) == []


def test_resolver_prefers_verified_stage_over_source_checkout(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    source = dist.parents[2]
    (source / "pyproject.toml").write_text("[build-system]", encoding="utf-8")
    package = tmp_path / "package" / "static"
    stage_assets(dist, package)
    assert resolve_workspace_static_dir(
        package_dir=package, checkout_root=source
    ) == package


def test_resolver_allows_source_build_only_for_real_checkout(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    checkout = dist.parents[2]
    (checkout / "pyproject.toml").write_text("[build-system]", encoding="utf-8")
    missing_package = tmp_path / "no-package"
    assert resolve_workspace_static_dir(
        package_dir=missing_package, checkout_root=checkout
    ) == dist
    (checkout / "pyproject.toml").unlink()
    with pytest.raises(WorkspaceAssetsError, match="unavailable"):
        resolve_workspace_static_dir(package_dir=missing_package, checkout_root=checkout)


def test_invalid_or_tampered_stage_never_falls_back_silently(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    checkout = dist.parents[2]
    (checkout / "pyproject.toml").write_text("[build-system]", encoding="utf-8")
    package = tmp_path / "package" / "static"
    stage_assets(dist, package)
    (package / "assets" / "app.js").write_text("tampered", encoding="utf-8")
    with pytest.raises(WorkspaceAssetsError, match="checksum"):
        resolve_workspace_static_dir(package_dir=package, checkout_root=checkout)
    with pytest.raises(WorkspaceAssetsError, match="checksum"):
        stage_assets(dist, package)
    (package / ASSET_MANIFEST).unlink()
    with pytest.raises(WorkspaceAssetsError, match="manifest"):
        resolve_workspace_static_dir(package_dir=package, checkout_root=checkout)


@pytest.mark.parametrize("removed", ["index.html", "assets/app.js"])
def test_partial_stage_rejected(tmp_path: Path, removed: str) -> None:
    dist = _vite_fixture(tmp_path)
    target = tmp_path / "static"
    stage_assets(dist, target)
    (target / removed).unlink()
    with pytest.raises(WorkspaceAssetsError):
        verify_staged_workspace_assets(target)


def test_stage_missing_vite_entrypoint_and_assets_rejected(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(WorkspaceAssetsError, match="missing"):
        stage_assets(dist, tmp_path / "static")
    (dist / "index.html").write_text("empty", encoding="utf-8")
    (dist / "assets").mkdir()
    with pytest.raises(WorkspaceAssetsError):
        stage_assets(dist, tmp_path / "static")


@pytest.mark.parametrize(
    "external",
    [
        '<script src="https://third-party.example/app.js"></script>',
        '<link href="//third-party.example/style.css" rel="stylesheet">',
        '<script src="/src/main.tsx"></script>',
        '<script src="/assets/missing.js"></script>',
    ],
)
def test_external_or_missing_entrypoint_resources_rejected(
    tmp_path: Path, external: str,
) -> None:
    dist = _vite_fixture(tmp_path)
    (dist / "index.html").write_text("<html>" + external + "</html>", encoding="utf-8")
    with pytest.raises(WorkspaceAssetsError):
        stage_assets(dist, tmp_path / "static")


def test_source_maps_and_external_css_urls_rejected(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    (dist / "assets" / "app.js.map").write_text("possibly private source", encoding="utf-8")
    with pytest.raises(WorkspaceAssetsError, match="unsupported"):
        stage_assets(dist, tmp_path / "static")
    (dist / "assets" / "app.js.map").unlink()
    (dist / "assets" / "app.css").write_text(
        "body { background: url(https://tracking.example/a.png) }", encoding="utf-8"
    )
    with pytest.raises(WorkspaceAssetsError, match="external CSS"):
        stage_assets(dist, tmp_path / "static")


def test_manifest_refuses_extra_unlisted_file(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    target = tmp_path / "static"
    stage_assets(dist, target)
    (target / "unlisted.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(WorkspaceAssetsError, match="do not match"):
        verify_staged_workspace_assets(target)


def test_manifest_is_versioned_and_contains_no_absolute_paths(tmp_path: Path) -> None:
    dist = _vite_fixture(tmp_path)
    target = tmp_path / "static"
    stage_assets(dist, target)
    payload = json.loads((target / ASSET_MANIFEST).read_text("utf-8"))
    assert payload["schema_version"] == "workspace-static-assets-v1"
    assert set(payload["files"]) == {"index.html", "assets/app.css", "assets/app.js"}
    assert str(tmp_path) not in json.dumps(payload)


def test_missing_packaged_ui_fails_with_actionable_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import evalops.workspace.assets as assets

    def fail() -> Path:
        raise WorkspaceAssetsError("private source path should never be exposed")

    monkeypatch.setattr(assets, "resolve_workspace_static_dir", fail)
    assert run_workspace_command(root=tmp_path, port=18081, open_browser=False) == 2
    message = capsys.readouterr().err
    assert "run scripts/stage_workspace_assets.py" in message
    assert "private source path" not in message
