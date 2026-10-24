#!/usr/bin/env python3
"""Verify a built EvalOps wheel using a clean venv outside the source checkout.

Run after Vite build + deterministic static staging + python -m build.
Never modifies production Workspace data, publishes artifacts or accesses cloud APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
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

STATIC = "evalops/workspace/static/"


def inspect_wheel(wheel: Path) -> dict[str, str]:
    """Verify the actual wheel members before installing."""

    with zipfile.ZipFile(wheel) as archive:
        files = set(archive.namelist())
        manifest_path = STATIC + "assets-manifest.json"
        if manifest_path not in files:
            raise RuntimeError("wheel has no static manifest")
        payload = json.loads(archive.read(manifest_path))
        if payload.get("schema_version") != "workspace-static-assets-v1":
            raise RuntimeError("wheel static schema is invalid")
        checksums: Any = payload.get("files")
        if not isinstance(checksums, dict) or not checksums:
            raise RuntimeError("wheel static file manifest is invalid")
        listed = {STATIC + name for name in checksums}
        actual = {name for name in files if name.startswith(STATIC) and name != manifest_path}
        if listed != actual:
            raise RuntimeError("wheel static listing does not match package members")
        if STATIC + "index.html" not in files or not any(
            name.startswith(STATIC + "assets/") for name in listed
        ):
            raise RuntimeError("wheel has no complete static UI")
        for name, digest in checksums.items():
            if (
                not isinstance(name, str)
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or hashlib.sha256(archive.read(STATIC + name)).hexdigest() != digest
                or name.endswith(".map")
            ):
                raise RuntimeError("wheel contains invalid or mismatched staged asset")
        return checksums


def _run(*args: str, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        args, cwd=cwd, env=env, text=True, capture_output=True, check=False, timeout=120
    )
    if completed.returncode != 0:
        # Do not expose arbitrary install logs from user-controlled package paths.
        raise RuntimeError("isolated wheel command failed: " + args[1])
    return completed.stdout


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


class RunningWorkspace:
    def __init__(self, python: Path, directory: Path, workspace_root: Path, env: dict[str, str]):
        self.port = _free_port()
        self.base = "http://127.0.0.1:" + str(self.port)
        self.process = subprocess.Popen(
            [
                str(python), "-u", "-m", "evalops", "workspace", "--no-open",
                "--root", str(workspace_root), "--port", str(self.port),
            ],
            cwd=directory, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=1,
        )
        self.output: queue.Queue[str] = queue.Queue()
        self.reader = threading.Thread(target=self._capture, daemon=True)
        self.reader.start()
        self.nonce = self._bootstrap_nonce()

    def _capture(self) -> None:
        if self.process.stdout is not None:
            for line in self.process.stdout:
                self.output.put(line)

    def _bootstrap_nonce(self) -> str:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                line = self.output.get(timeout=0.5).strip()
            except queue.Empty as error:
                if self.process.poll() is not None:
                    raise RuntimeError("installed Workspace exited before bootstrap") from error
                continue
            match = re.fullmatch(re.escape(self.base) + r"/#bootstrap=([A-Za-z0-9_-]+)", line)
            if match:
                return match.group(1)
        raise RuntimeError("installed Workspace did not emit bootstrap URL")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def _request(
    opener: urllib.request.OpenerDirector,
    base: str,
    path: str,
    *,
    data: dict[str, object] | None = None,
) -> tuple[int, bytes]:
    headers = {}
    content = None
    if data is not None:
        content = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Origin"] = base
    req = urllib.request.Request(
        base + path, data=content, headers=headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with opener.open(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _health(opener: urllib.request.OpenerDirector, base: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status, _ = _request(opener, base, "/")
            if status == 200:
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("installed Workspace loopback server did not become healthy")


def verify_clean_wheel(wheel: Path) -> dict[str, object]:
    hashes = inspect_wheel(wheel)
    with tempfile.TemporaryDirectory(prefix="evalops-clean-wheel-") as temp:
        root = Path(temp)
        venv_root = root / "isolated-python"
        storage = root / "private-workspace"
        outside = root / "outside-source"
        outside.mkdir()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        # Prove the installed Python runtime is usable without a Node executable
        # anywhere on its executable search path.
        scripts_dir = venv_root / ("Scripts" if os.name == "nt" else "bin")
        node_free_path = str(scripts_dir)
        if os.name == "nt":
            node_free_path += os.pathsep + str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32")
        environment["PATH"] = node_free_path
        if shutil.which("node", path=node_free_path) is not None:
            raise RuntimeError("Node is unexpectedly available to clean wheel process")
        venv.EnvBuilder(with_pip=True).create(venv_root)
        python = _python_path(venv_root)
        _run(str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", str(wheel.resolve()) + "[workspace]", cwd=outside, env=environment)
        help_text = _run(str(python), "-m", "evalops", "--help", cwd=outside, env=environment)
        if "workspace" not in help_text or "retrieval" not in help_text:
            raise RuntimeError("installed core CLI is incomplete")

        location = _run(
            str(python), "-c",
            "import evalops.workspace.assets as a; print(a.resolve_workspace_static_dir())",
            cwd=outside, env=environment,
        ).strip()
        if not Path(location).is_relative_to(venv_root):
            raise RuntimeError("installed UI resources resolved outside clean venv")

        browser = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        first = RunningWorkspace(python, outside, storage, environment)
        try:
            _health(browser, first.base)
            status, html = _request(browser, first.base, "/")
            if status != 200 or b"EvalOps Local Workspace" not in html:
                raise RuntimeError("installed UI entrypoint not served")
            for match in re.findall(rb'(?:src|href)="/(assets/[^"]+)"', html):
                asset = match.decode("utf-8")
                code, binary = _request(browser, first.base, "/" + asset)
                if code != 200 or hashlib.sha256(binary).hexdigest() != hashes.get(asset):
                    raise RuntimeError("installed UI asset mismatch")
            code, _ = _request(
                browser, first.base, "/api/v1/session/bootstrap", data={"nonce": first.nonce}
            )
            if code != 200:
                raise RuntimeError("installed bootstrap exchange failed")
            code, raw = _request(browser, first.base, "/api/v1/health")
            if code != 200 or json.loads(raw) != {"status": "ok"}:
                raise RuntimeError("installed authenticated health failed")
            code, raw = _request(
                browser, first.base, "/api/v1/workspaces",
                data={"display_name": "clean wheel persistence"},
            )
            if code != 201:
                raise RuntimeError("installed Workspace could not create local data")
            created_id = json.loads(raw)["workspace_id"]
        finally:
            first.close()

        second = RunningWorkspace(python, outside, storage, environment)
        try:
            _health(urllib.request.build_opener(), second.base)
            code, _ = _request(browser, second.base, "/api/v1/workspaces")
            if code != 401:
                raise RuntimeError("old process session unexpectedly survived restart")
            code, _ = _request(
                browser, second.base, "/api/v1/session/bootstrap", data={"nonce": first.nonce}
            )
            if code != 401:
                raise RuntimeError("old bootstrap unexpectedly survived restart")
            code, _ = _request(
                browser, second.base, "/api/v1/session/bootstrap", data={"nonce": second.nonce}
            )
            if code != 200:
                raise RuntimeError("new process bootstrap could not authenticate")
            code, raw = _request(browser, second.base, "/api/v1/workspaces")
            if code != 200 or created_id not in {
                row["workspace_id"] for row in json.loads(raw)["workspaces"]
            }:
                raise RuntimeError("installed Workspace data did not survive restart")
        finally:
            second.close()

    return {
        "wheel_verified": True,
        "static_asset_count": len(hashes),
        "clean_install": True,
        "installed_ui": True,
        "fresh_sessions": True,
        "persistent_local_metadata": True,
        "no_node_runtime_invocation": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an EvalOps wheel installed outside source")
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    try:
        if not args.wheel.is_file():
            raise RuntimeError("specified wheel does not exist")
        result = verify_clean_wheel(args.wheel)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        print("Wheel verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
