"""Register validated imported or referenced retrieval input with private provenance."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from evalops.workspace.ingestion.csv_adapter import normalize_retrieval_csv_bytes
from evalops.workspace.ingestion.jsonl import validate_retrieval_jsonl
from evalops.workspace.ingestion.models import (
    MAX_INPUT_BYTES,
    CsvMapping,
    InputKind,
    InputManifest,
    InputRegistrationResult,
    InputSourceMode,
    InputValidationError,
    InputValidationSummary,
)
from evalops.workspace.storage import WorkspaceStore


def _require_jsonl(filename: str | None) -> None:
    if filename is None or Path(filename).suffix.lower() != ".jsonl":
        raise InputValidationError("UNSUPPORTED_FORMAT", "only .jsonl retrieval input is supported")


def _persist_imported(
    store: WorkspaceStore,
    workspace_id: str,
    *,
    kind: InputKind,
    canonical: bytes,
    summary: InputValidationSummary,
    source_sha256: str,
    source_filename: str,
) -> InputRegistrationResult:
    input_id = f"input-{uuid.uuid4().hex}"
    relative_path = store.save_imported_input(workspace_id, input_id, canonical)
    manifest = InputManifest(
        input_id=input_id,
        kind=kind,
        source_mode=InputSourceMode.IMPORTED,
        content_sha256=summary.content_sha256,
        source_sha256=source_sha256,
        record_count=summary.record_count,
        stored_relative_path=relative_path,
        source_filename=Path(source_filename.replace("\\", "/")).name,
        created_at=datetime.now(UTC),
    )
    try:
        store.save_input_manifest(workspace_id, manifest)
    except Exception:
        store.discard_imported_input(workspace_id, input_id)
        raise
    return InputRegistrationResult(manifest=manifest, summary=summary)


def register_imported_jsonl(
    store: WorkspaceStore,
    workspace_id: str,
    *,
    kind: InputKind,
    data: bytes,
    source_filename: str,
) -> InputRegistrationResult:
    """Validate upload bytes before writing anything in canonical imported storage."""

    store.get_workspace(workspace_id)
    _require_jsonl(source_filename)
    summary = validate_retrieval_jsonl(data, kind)
    return _persist_imported(
        store,
        workspace_id,
        kind=kind,
        canonical=data,
        summary=summary,
        source_sha256=summary.content_sha256,
        source_filename=source_filename,
    )


def register_imported_csv(
    store: WorkspaceStore,
    workspace_id: str,
    *,
    kind: InputKind,
    data: bytes,
    source_filename: str,
    mapping: CsvMapping,
) -> InputRegistrationResult:
    """Persist only validated canonical JSONL, never the raw CSV bytes."""

    store.get_workspace(workspace_id)
    if Path(source_filename).suffix.lower() != ".csv":
        raise InputValidationError("UNSUPPORTED_FORMAT", "only .csv source input is supported")
    canonical, summary = normalize_retrieval_csv_bytes(data, kind=kind, mapping=mapping)
    return _persist_imported(
        store,
        workspace_id,
        kind=kind,
        canonical=canonical,
        summary=summary,
        source_sha256=hashlib.sha256(data).hexdigest(),
        source_filename=source_filename,
    )


def register_referenced_jsonl(
    store: WorkspaceStore,
    workspace_id: str,
    *,
    kind: InputKind,
    source: Path,
) -> InputRegistrationResult:
    """Resolve an explicit local file and persist its private path and checksum."""

    store.get_workspace(workspace_id)
    _require_jsonl(source.name)
    try:
        resolved = source.resolve(strict=True)
        if not resolved.is_file():
            raise InputValidationError("NOT_A_FILE", "referenced input must be a regular file")
        if resolved.stat().st_size > MAX_INPUT_BYTES:
            raise InputValidationError("INPUT_TOO_LARGE", "input exceeds 10 MiB limit")
        data = resolved.read_bytes()
        if len(data) > MAX_INPUT_BYTES:
            raise InputValidationError("INPUT_TOO_LARGE", "input exceeds 10 MiB limit")
    except InputValidationError:
        raise
    except (OSError, RuntimeError) as error:
        raise InputValidationError("UNREADABLE_INPUT", "referenced input cannot be read") from error
    summary = validate_retrieval_jsonl(data, kind)
    manifest = InputManifest(
        input_id=f"input-{uuid.uuid4().hex}",
        kind=kind,
        source_mode=InputSourceMode.REFERENCED,
        content_sha256=summary.content_sha256,
        source_sha256=summary.content_sha256,
        record_count=summary.record_count,
        source_path=str(resolved),
        source_filename=resolved.name,
        created_at=datetime.now(UTC),
    )
    store.save_input_manifest(workspace_id, manifest)
    return InputRegistrationResult(manifest=manifest, summary=summary)
