"""Reuse the authoritative retrieval JSONL loaders for local validation."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from evalops.datasets.io import load_retrieval_ground_truth, load_retrieval_predictions
from evalops.workspace.ingestion.models import (
    InputKind,
    InputValidationError,
    InputValidationSummary,
)


def validate_retrieval_jsonl(data: bytes, kind: InputKind) -> InputValidationSummary:
    """Validate captured bytes, not a subsequently mutable source path."""

    if not data.strip():
        raise InputValidationError("EMPTY_INPUT", "retrieval input must contain records")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InputValidationError("INVALID_UTF8", "retrieval input must be UTF-8") from error

    with tempfile.TemporaryDirectory(prefix="evalops-input-validation-") as directory:
        staged = Path(directory) / "input.jsonl"
        staged.write_bytes(data)
        try:
            if kind == InputKind.RETRIEVAL_GROUND_TRUTH:
                records = load_retrieval_ground_truth(staged)
            elif kind == InputKind.RETRIEVAL_PREDICTIONS:
                records = load_retrieval_predictions(staged)
            else:
                raise InputValidationError("UNSUPPORTED_KIND", "unsupported retrieval input kind")
        except ValueError as error:
            code = "DUPLICATE_QUERY_ID" if "duplicate query_id" in str(error) else "INVALID_JSONL"
            raise InputValidationError(code, "retrieval JSONL validation failed") from error
    if not records:
        raise InputValidationError("EMPTY_INPUT", "retrieval input must contain records")
    return InputValidationSummary(
        record_count=len(records),
        unique_query_count=len(records),
        content_sha256=hashlib.sha256(data).hexdigest(),
    )
