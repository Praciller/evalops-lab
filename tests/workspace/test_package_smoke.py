"""Inspect the actual wheel's complete packaged frontend, not source dist paths."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from scripts.verify_workspace_wheel import (
    STATIC_PREFIX,
    WheelVerificationError,
    inspect_wheel,
)


def _fixture_wheel(
    tmp_path: Path, *, missing: bool = False, tampered: bool = False, extra: bool = False
) -> Path:
    wheel = tmp_path / "evalops_lab-0.1.0-py3-none-any.whl"
    files = {
        "index.html": b'<html><script src="/assets/app.js"></script></html>',
        "assets/app.js": b"console.log('packaged');",
    }
    manifest = {
        "schema_version": "workspace-static-assets-v1",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            if missing and name == "assets/app.js":
                continue
            if tampered and name == "assets/app.js":
                data += b"tampered"
            archive.writestr(STATIC_PREFIX + name, data)
        archive.writestr(
            STATIC_PREFIX + "assets-manifest.json",
            json.dumps(manifest, sort_keys=True),
        )
        if extra:
            archive.writestr(STATIC_PREFIX + "assets/extra.js", b"unlisted")
    return wheel


def test_wheel_contains_exact_checksum_verified_html_and_assets(tmp_path: Path) -> None:
    manifest = inspect_wheel(_fixture_wheel(tmp_path))
    assert set(manifest) == {"index.html", "assets/app.js"}
    assert len(manifest["index.html"]) == 64


@pytest.mark.parametrize("case", ["missing", "tampered", "extra"])
def test_wheel_refuses_incomplete_or_unmanifested_bundle(tmp_path: Path, case: str) -> None:
    with pytest.raises(WheelVerificationError):
        inspect_wheel(_fixture_wheel(tmp_path, **{case: True}))


def test_wheel_must_exist_and_be_a_real_zip(tmp_path: Path) -> None:
    with pytest.raises(WheelVerificationError):
        inspect_wheel(tmp_path / "missing.whl")
    fake = tmp_path / "fake.whl"
    fake.write_text("not a wheel", encoding="utf-8")
    with pytest.raises(WheelVerificationError):
        inspect_wheel(fake)


def test_real_wheel_when_provided_by_package_pipeline() -> None:
    wheel = os.environ.get("EVALOPS_WHEEL_PATH")
    if wheel is None:
        pytest.skip("wheel path is supplied by the packaging acceptance pipeline")
    content = inspect_wheel(Path(wheel))
    assert "index.html" in content
    assert any(name.startswith("assets/") for name in content)
