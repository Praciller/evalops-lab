"""Inspect wheel package-data without importing from the source checkout."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.verify_workspace_wheel import inspect_wheel

PREFIX = "evalops/workspace/static/"


def _wheel(
    path: Path, *, tampered: bool = False, source_map: bool = False,
    omit_index: bool = False
) -> Path:
    outputs = {
        "index.html": b'<html><script src="/assets/app.js"></script></html>',
        "assets/app.js": b"console.log('test-only')",
    }
    if source_map:
        outputs["assets/app.js.map"] = b"unwanted source map"
    manifest = {
        "schema_version": "workspace-static-assets-v1",
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(outputs.items())},
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            PREFIX + "assets-manifest.json",
            json.dumps(manifest, sort_keys=True).encode("utf-8"),
        )
        for name, raw in outputs.items():
            if omit_index and name == "index.html":
                continue
            archive.writestr(PREFIX + name, b"tampered" if tampered and name == "assets/app.js" else raw)
    return path


def test_wheel_inventory_validates_all_digests(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "valid.whl")
    actual = inspect_wheel(wheel)
    assert set(actual) == {"index.html", "assets/app.js"}
    assert actual["assets/app.js"] == hashlib.sha256(b"console.log('test-only')").hexdigest()


@pytest.mark.parametrize(
    "variant", ["tampered", "source_map", "omit_index"]
)
def test_wheel_rejects_tampered_or_missing_assets(tmp_path: Path, variant: str) -> None:
    wheel = _wheel(
        tmp_path / "bad.whl",
        tampered=variant == "tampered",
        source_map=variant == "source_map",
        omit_index=variant == "omit_index",
    )
    with pytest.raises(RuntimeError):
        inspect_wheel(wheel)


def test_wheel_rejects_wrong_version(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "invalid.whl")
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(PREFIX + "assets-manifest.json", '{"schema_version":"unknown","files":{}}')
    with pytest.raises(RuntimeError):
        inspect_wheel(wheel)
