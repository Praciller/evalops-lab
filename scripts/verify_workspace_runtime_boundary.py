#!/usr/bin/env python3
"""Fail closed on unsafe runtime content in built Workspace UI, stage and wheel.

Static checks complement the actual no-external-request packaged browser proof.
No data files, tokens, network connections or deployment APIs are accessed.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC_PREFIX = "evalops/workspace/static/"
_FORBIDDEN_PATH = re.compile(
    r"(?i)(?:[a-z]:[/\\](?:users|documents)[/\\]|/home/[^/\s\"']+/|"
    r"/users/[^/\s\"']+/|file://)"
)
_SECRET = re.compile(
    r"(?i)(?:sk-proj-[a-z0-9_-]{16,}|sk-[a-z0-9_-]{24,}|"
    r"AIza[0-9a-z_-]{35}|(?:openai|gemini|aws_secret_access)_?api?_?key"
    r"\s*[:=]\s*['\"][^'\"]{8,})"
)
_URL = re.compile(r"https?://[^\s\"'\`<>\\]+", re.IGNORECASE)
_DIRECT_REQUEST = re.compile(
    r"(?i)(?:\bfetch|\bWebSocket|\bEventSource|\bsendBeacon)"
    r"\s*\(\s*['\"\`]https?://"
)
# Known harmless literal namespaces and framework error-documentation pointers.
# These are not network requests. Direct-request sinks still reject these URLs.
_INERT_URL_PREFIXES = (
    "http://www.w3.org/",
    "https://www.w3.org/",
    "https://react.dev/errors/",
    "https://reactrouter.com/",
    "https://json-schema.org/draft/",
    "http://json-schema.org/draft-",
    "https://json-schema.org/draft-",
)


class RuntimeBoundaryError(ValueError):
    """A distributable artifact contains prohibited runtime material."""


def scan_content(name: str, content: bytes) -> None:
    """Enforce path/secret/no-external-URL constraints on one runtime asset."""
    if name.endswith(".map") or ".map?" in name:
        raise RuntimeBoundaryError("source map must not ship")
    if b"\x00" in content:
        raise RuntimeBoundaryError("binary/non-text runtime asset requires explicit review")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeBoundaryError("non-text runtime asset requires review") from error
    if _FORBIDDEN_PATH.search(text):
        raise RuntimeBoundaryError("developer absolute path or local file URI in runtime bundle")
    if _SECRET.search(text):
        raise RuntimeBoundaryError("secret-like credential literal in runtime bundle")
    if "0.0.0.0" in text:
        raise RuntimeBoundaryError("non-loopback host literal in runtime bundle")
    if re.search(r"apps[/\\]web[/\\]public[/\\]evidence", text, flags=re.IGNORECASE):
        raise RuntimeBoundaryError("automatic public evidence path reference is forbidden")
    if _DIRECT_REQUEST.search(text):
        raise RuntimeBoundaryError("runtime request contains an external URL")
    for url in _URL.findall(text):
        # The exact loopback placeholder is used by bundled client libraries
        # for URL parsing and is not an off-origin network destination.
        # Reject any URL with a path, port, credentials or lookalike hostname.
        inert_loopback = url in {"http://localhost", "http://localhost/"}
        # Bundled URL parsers assemble IPv6 origins with this inert JS placeholder.
        # Vite 8 Rolldown minifies this inert Zod IPv6 parser variable from n to e.
        # Accept only exact known parser placeholders; reject ports, paths and sinks.
        inert_url_parser_template = url in {
            "http://[${n}]",
            "http://[${n}]/",
            "http://[${e}]",
            "http://[${e}]/",
        }
        inert_documentation = any(url.startswith(prefix) for prefix in _INERT_URL_PREFIXES)
        if name.endswith((".html", ".css")) or not (
            inert_loopback or inert_url_parser_template or inert_documentation
        ):
            try:
                hostname = urlsplit(url).hostname or "invalid"
            except ValueError:
                hostname = "unparseable"
            safe_host = re.sub(r"[^a-z0-9.-]", "", hostname.lower())[:80]
            raise RuntimeBoundaryError(
                f"external URL host {safe_host} in runtime asset {Path(name).name}"
            )


def read_dist(root: Path) -> dict[str, bytes]:
    """Collect all production build files without following symlinks."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeBoundaryError("frontend build is unavailable")
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeBoundaryError("build output contains a symlink")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    if "index.html" not in files or not any(n.startswith("assets/") for n in files):
        raise RuntimeBoundaryError("frontend build is incomplete")
    return files


def verify_runtime_boundary(dist: Path, staged: Path, wheel: Path) -> int:
    """Check all three surfaces and assert staged/wheel bytes match the source build."""
    from evalops.workspace.assets import verify_staged_workspace_assets

    built = read_dist(dist)
    stage_files = verify_staged_workspace_assets(staged)
    if not wheel.is_file() or not zipfile.is_zipfile(wheel):
        raise RuntimeBoundaryError("built wheel is unavailable")
    for name, content in built.items():
        scan_content(name, content)
    for name in stage_files:
        contents = (staged / name).read_bytes()
        scan_content(name, contents)
        if built.get(name) != contents:
            raise RuntimeBoundaryError("staged asset differs from frontend build")
    with zipfile.ZipFile(wheel) as archive:
        names = {
            name[len(STATIC_PREFIX) :]
            for name in archive.namelist()
            if name.startswith(STATIC_PREFIX) and not name.endswith("/")
        }
        if names != set(stage_files) | {"assets-manifest.json"}:
            raise RuntimeBoundaryError("wheel files differ from staged manifest")
        for name in names:
            content = archive.read(STATIC_PREFIX + name)
            if name == "assets-manifest.json":
                if content != (staged / name).read_bytes():
                    raise RuntimeBoundaryError("wheel manifest differs from staged manifest")
            else:
                scan_content(name, content)
                if content != built[name]:
                    raise RuntimeBoundaryError("wheel asset differs from frontend build")
    return len(built)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "apps" / "workspace" / "dist")
    parser.add_argument(
        "--staged", type=Path, default=ROOT / "src" / "evalops" / "workspace" / "static"
    )
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = verify_runtime_boundary(args.dist, args.staged, args.wheel)
    except (RuntimeBoundaryError, OSError, ValueError, KeyError) as error:
        print(f"RUNTIME_BOUNDARY_FAILED: {error}", file=sys.stderr)
        return 1
    print(f"RUNTIME_BOUNDARY_OK: inspected {count} build files and exact staged/wheel assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
