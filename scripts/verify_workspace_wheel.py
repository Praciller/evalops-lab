#!/usr/bin/env python3
"""Verify a real Workspace wheel in a fresh venv, outside the source checkout.

Source builds may require Node. This installed runtime launches only Python,
binds 127.0.0.1, reads packaged Vite resources and never publishes evidence.
Optional --browser executes a real packaged Playwright acceptance flow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path
from typing import Any

STATIC_PREFIX = "evalops/workspace/static/"
MANIFEST_NAME = STATIC_PREFIX + "assets-manifest.json"
SCHEMA_VERSION = "workspace-static-assets-v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


class WheelVerificationError(RuntimeError):
    """A packaged-runtime acceptance requirement failed."""


def inspect_wheel(wheel: Path) -> dict[str, str]:
    """Require exact asset manifest coverage and intact bytes in the built wheel."""
    if not wheel.is_file() or wheel.suffix != ".whl" or not zipfile.is_zipfile(wheel):
        raise WheelVerificationError("a valid built .whl file is required")
    with zipfile.ZipFile(wheel) as archive:
        if archive.testzip() is not None:
            raise WheelVerificationError("wheel ZIP integrity failed")
        names = {
            name[len(STATIC_PREFIX):]
            for name in archive.namelist()
            if name.startswith(STATIC_PREFIX) and not name.endswith("/")
        }
        if "assets-manifest.json" not in names:
            raise WheelVerificationError("packaged static asset manifest is missing")
        try:
            document: Any = json.loads(archive.read(MANIFEST_NAME))
        except (KeyError, ValueError, UnicodeError) as error:
            raise WheelVerificationError("packaged static manifest is invalid") from error
        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
            raise WheelVerificationError("packaged static manifest schema mismatch")
        files = document.get("files")
        if not isinstance(files, dict) or not files:
            raise WheelVerificationError("packaged static file listing is empty")
        if set(files) != names - {"assets-manifest.json"}:
            raise WheelVerificationError("wheel files differ from the static manifest")
        if "index.html" not in files or not any(
            name.startswith("assets/") for name in files
        ):
            raise WheelVerificationError("wheel frontend is incomplete")
        for name, expected in files.items():
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[a-zA-Z0-9_./-]+", name)
                or name.startswith("/")
                or ".." in Path(name).parts
                or name.endswith(".map")
                or not isinstance(expected, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            ):
                raise WheelVerificationError("unsafe packaged file or digest")
            actual = hashlib.sha256(archive.read(STATIC_PREFIX + name)).hexdigest()
            if actual != expected:
                raise WheelVerificationError("packaged static SHA-256 mismatch")
        html = archive.read(STATIC_PREFIX + "index.html").decode("utf-8")
        if "<html" not in html.lower() or "/assets/" not in html:
            raise WheelVerificationError("packaged HTML entrypoint is invalid")
        return dict(sorted(files.items()))


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, text=True, encoding="utf-8",
            capture_output=True, check=True, timeout=180,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise WheelVerificationError(f"subprocess verification failed: {args[0]}") from error
    return result.stdout


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout is not None:
        process.stdout.close()


def _serve(
    python: Path, root: Path, cwd: Path, port: int
) -> tuple[subprocess.Popen[str], str]:
    command = [
        str(python), "-I", "-u", "-m", "evalops", "workspace",
        "--no-open", "--root", str(root), "--port", str(port),
    ]
    env = {**os.environ, "PYTHONPATH": "", "PYTHONUNBUFFERED": "1"}
    process = subprocess.Popen(
        command, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    output: queue.Queue[str] = queue.Queue()

    def collect_output() -> None:
        if process.stdout is not None:
            for line in process.stdout:
                output.put(line.strip())

    threading.Thread(target=collect_output, daemon=True).start()
    bootstrap: str | None = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise WheelVerificationError("installed workspace process exited early")
            try:
                line = output.get(timeout=0.25)
                match = re.search(
                    rf"http://127\.0\.0\.1:{port}/#bootstrap=[^\s]+", line
                )
                if match:
                    bootstrap = match.group(0)
            except queue.Empty:
                pass
            if bootstrap:
                try:
                    with opener.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                        html = response.read(500_000).decode("utf-8")
                    if "<html" in html.lower() and "/assets/" in html:
                        return process, bootstrap
                except (urllib.error.URLError, TimeoutError, UnicodeError):
                    pass
        raise WheelVerificationError("installed Workspace did not serve packaged HTML")
    except Exception:
        _stop(process)
        raise


def _persist_workspace(python: Path, root: Path, cwd: Path) -> str:
    code = (
        "import sys; from pathlib import Path; "
        "from evalops.workspace.storage import WorkspaceStore; "
        "s=WorkspaceStore(Path(sys.argv[1])); "
        "print(s.create_workspace('Packaged restart persistence').workspace_id)"
    )
    return _run([str(python), "-I", "-c", code, str(root)], cwd=cwd).strip()


def _check_persisted(python: Path, root: Path, workspace_id: str, cwd: Path) -> None:
    code = (
        "import sys; from pathlib import Path; "
        "from evalops.workspace.storage import WorkspaceStore; "
        "s=WorkspaceStore(Path(sys.argv[1])); "
        "assert s.get_workspace(sys.argv[2]).workspace_id == sys.argv[2]"
    )
    _run([str(python), "-I", "-c", code, str(root), workspace_id], cwd=cwd)


def verify_wheel(wheel: Path, *, browser: bool = False) -> None:
    inspect_wheel(wheel)
    wheel = wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="evalops-installed-wheel-") as temp:
        outside = Path(temp)
        environment = outside / "isolated-venv"
        root = outside / "persisted-workspace"
        cwd = outside / "outside-checkout"
        cwd.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        _run(
            [str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", f"{wheel}[workspace]"],
            cwd=cwd,
        )
        _run([str(python), "-I", "-m", "evalops", "--help"], cwd=cwd)
        code = (
            "import sys; from pathlib import Path; "
            "from evalops.workspace.assets import resolve_workspace_static_dir, "
            "verify_staged_workspace_assets; "
            "from evalops import __file__ as source; "
            "root=resolve_workspace_static_dir(); "
            "assert root.is_relative_to(Path(sys.prefix).resolve()); "
            "assert Path(source).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "assert verify_staged_workspace_assets(root)"
        )
        _run([str(python), "-I", "-c", code], cwd=cwd)

        first, first_url = _serve(python, root, cwd, _free_port())
        try:
            if browser:
                npm = shutil.which("npm")
                if npm is None:
                    raise WheelVerificationError("Node is required only for browser tests")
                destination = outside / "browser-export"
                destination.mkdir()
                env = {
                    **os.environ,
                    "EVALOPS_PACKAGED_BOOTSTRAP_URL": first_url,
                    "EVALOPS_PACKAGED_BASE_URL": first_url.split("/#")[0],
                    "EVALOPS_PACKAGED_DESTINATION": str(destination),
                }
                _run(
                    [npm, "run", "test:e2e:packaged"],
                    cwd=REPO_ROOT / "apps" / "workspace", env=env,
                )
                registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
                if not registry.get("workspace_ids"):
                    raise WheelVerificationError("packaged browser did not persist workspace")
        finally:
            _stop(first)

        persisted_id = _persist_workspace(python, root, cwd)
        second, second_url = _serve(python, root, cwd, _free_port())
        try:
            if first_url.split("#bootstrap=")[1] == second_url.split("#bootstrap=")[1]:
                raise WheelVerificationError("restart reused an invalid bootstrap nonce")
            _check_persisted(python, root, persisted_id, cwd)
        finally:
            _stop(second)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="already built, staged Python wheel")
    parser.add_argument("--browser", action="store_true", help="also run installed-browser E2E")
    args = parser.parse_args()
    try:
        verify_wheel(args.wheel, browser=args.browser)
    except WheelVerificationError as error:
        print(f"WHEEL_VERIFICATION_FAILED: {error}", file=sys.stderr)
        return 1
    print("WHEEL_VERIFICATION_OK: clean install, packaged UI, loopback, restart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
