"""Shared non-destructive snapshot preparation for external datasets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_to_temporary(source: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            with urlopen(source, timeout=60) as response:  # noqa: S310 - explicit user-supplied source
                shutil.copyfileobj(response, handle)
        else:
            source_path = Path(source)
            if not source_path.is_file():
                raise FileNotFoundError(f"source does not exist: {source_path}")
            with source_path.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
    except Exception:
        handle.close()
        temporary.unlink(missing_ok=True)
        raise
    handle.close()
    return temporary


def prepare_source(source: str, destination: Path, expected_sha256: str | None = None) -> str:
    """Copy/download one snapshot, refusing ambiguous or destructive overwrites."""

    if destination.exists():
        existing_digest = sha256_file(destination)
        if expected_sha256 and existing_digest == expected_sha256:
            return existing_digest
        if (
            not expected_sha256
            and Path(source).is_file()
            and existing_digest == sha256_file(Path(source))
        ):
            return existing_digest
        raise FileExistsError(
            f"destination already exists with a different checksum: {destination}; "
            "move it aside manually before retrying"
        )

    temporary = _copy_to_temporary(source, destination)
    digest = sha256_file(temporary)
    if expected_sha256 and digest != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch: expected {expected_sha256}, got {digest}")
    os.replace(temporary, destination)
    return digest
