"""Exercise the Pages doctor through its command-line entry point."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_pages_output.py"
EVIDENCE = "evidence/artifacts/demo-run.json"
INDEX = "evidence/index.json"
BUILD_FILES = {
    "_next/static/chunks/demo.js": ".next/static/chunks/demo.js",
    "storybook/index.html": "storybook-public-static/index.html",
    "storybook/index.json": "storybook-public-static/index.json",
}


def write(root: Path, relative: str, contents: str = "synthetic fixture") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


@pytest.fixture
def web(tmp_path: Path) -> Path:
    web = tmp_path / "apps" / "web"
    index_json = json.dumps({"artifacts": [{"artifact_id": "demo-run", "artifact_type": "run"}]})
    for folder in ("public", "out"):
        write(web, f"{folder}/{INDEX}", index_json)
        write(web, f"{folder}/{EVIDENCE}")
    for built, source in BUILD_FILES.items():
        write(web, source)
        write(web, f"out/{built}")
    for route, page in (
        ("", "__next.__PAGE__.txt"),
        ("runs/", "__next.runs.__PAGE__.txt"),
        ("runs/demo-run/", "__next.runs.$d$artifactId.__PAGE__.txt"),
        ("comparisons/", "__next.comparisons.__PAGE__.txt"),
        ("_not-found/", "__next._not-found.__PAGE__.txt"),
    ):
        for filename in ("index.html", "index.txt", "__next._tree.txt", "__next._full.txt", page):
            write(web, f"out/{route}{filename}")
    for filename in ("404.html", "404/index.html"):
        write(web, f"out/{filename}")
    return web


def run_checker(web: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER)], cwd=web.parents[1], capture_output=True, text=True
    )


def test_accepts_expected_files_and_prints_evidence_hashes(web: Path) -> None:
    result = run_checker(web)
    expected = hashlib.sha256((web / "public" / EVIDENCE).read_bytes()).hexdigest()
    assert result.returncode == 0, result.stderr
    assert f"{expected}  {EVIDENCE}" in result.stdout
    assert "PAGES_OUTPUT_OK" in result.stdout


@pytest.mark.parametrize(
    ("relative", "diagnostic"),
    [
        ("public/evidence/extra.txt", "apps/web/public"),
        ("out/evidence/extra.txt", "out/evidence"),
        ("out/extra.txt", "Pages route output"),
        ("out/runs/demo-run/private/extra.json", "Pages route output"),
        ("out/_next/static/chunks/extra.js", "out/_next/static"),
        ("out/storybook/extra.json", "out/storybook"),
    ],
)
def test_rejects_unexpected_files_without_echoing_them(
    web: Path, relative: str, diagnostic: str
) -> None:
    write(web, relative, "synthetic private sentinel")
    result = run_checker(web)
    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert not result.stdout
    assert "synthetic private sentinel" not in result.stderr
    assert "extra." not in result.stderr


@pytest.mark.parametrize("relative", [EVIDENCE, *BUILD_FILES])
def test_rejects_modified_copies(web: Path, relative: str) -> None:
    write(web, f"out/{relative}", "different contents")
    result = run_checker(web)
    assert result.returncode == 1
    assert "bytes differ" in result.stderr
    assert not result.stdout


def test_rejects_missing_route(web: Path) -> None:
    (web / "out/runs/demo-run/index.html").unlink()
    result = run_checker(web)
    assert result.returncode == 1
    assert "missing file in Pages route output" in result.stderr


def test_rejects_duplicate_index_ids(web: Path) -> None:
    source = web / "public" / INDEX
    index = json.loads(source.read_bytes())
    index["artifacts"].append({"artifact_id": "DEMO-RUN", "artifact_type": "run"})
    for folder in ("public", "out"):
        write(web, f"{folder}/{INDEX}", json.dumps(index))
    result = run_checker(web)
    assert result.returncode == 1
    assert "duplicate public artifact ID" in result.stderr


def test_rejects_linked_export_root(web: Path) -> None:
    out = web / "out"
    target = web / "linked-build"
    out.rename(target)
    try:
        out.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("creating directory symlinks requires platform support and privileges")
    result = run_checker(web)
    assert result.returncode == 1
    assert "linked static directory" in result.stderr
