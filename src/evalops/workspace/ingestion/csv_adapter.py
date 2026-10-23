"""Guided CSV-to-canonical-JSONL normalization without formula execution."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from evalops.models.retrieval import RetrievalGroundTruth, RetrievalPrediction
from evalops.workspace.ingestion.jsonl import validate_retrieval_jsonl
from evalops.workspace.ingestion.models import (
    CsvMapping,
    InputKind,
    InputValidationError,
    InputValidationSummary,
)


def normalize_retrieval_csv(
    source: Path, *, kind: InputKind, mapping: CsvMapping
) -> tuple[bytes, InputValidationSummary]:
    try:
        data = source.read_bytes()
    except OSError as error:
        raise InputValidationError("UNREADABLE_INPUT", "CSV input cannot be read") from error
    return normalize_retrieval_csv_bytes(data, kind=kind, mapping=mapping)


def normalize_retrieval_csv_bytes(
    data: bytes, *, kind: InputKind, mapping: CsvMapping
) -> tuple[bytes, InputValidationSummary]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputValidationError("INVALID_UTF8", "CSV must be UTF-8") from error
    if not text.strip():
        raise InputValidationError("EMPTY_INPUT", "CSV must contain records")

    query_column = mapping.query_id_column.strip()
    document_column = mapping.document_ids_column.strip()
    if not query_column or not document_column or query_column == document_column:
        raise InputValidationError("INVALID_MAPPING", "CSV mapping requires distinct columns")
    normalized: list[str] = []
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        header = reader.fieldnames
        if header is None:
            raise InputValidationError("EMPTY_INPUT", "CSV must contain a header")
        stripped = [name.strip() for name in header]
        if len(stripped) != len(set(stripped)) or any(not name for name in stripped):
            raise InputValidationError("DUPLICATE_HEADERS", "CSV header names are invalid")
        if query_column not in stripped or document_column not in stripped:
            raise InputValidationError("MISSING_COLUMN", "CSV mapping column is missing")
        reader.fieldnames = stripped
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise InputValidationError("INVALID_CSV", "CSV row has incorrect column count")
            query_id = row[query_column].strip()
            document_ids = [
                token.strip()
                for token in row[document_column].split(mapping.document_ids_delimiter)
                if token.strip()
            ]
            record: RetrievalGroundTruth | RetrievalPrediction
            if kind == InputKind.RETRIEVAL_GROUND_TRUTH:
                record = RetrievalGroundTruth(query_id=query_id, relevant_document_ids=document_ids)
            elif kind == InputKind.RETRIEVAL_PREDICTIONS:
                record = RetrievalPrediction(query_id=query_id, retrieved_document_ids=document_ids)
            else:
                raise InputValidationError("UNSUPPORTED_KIND", "unsupported retrieval input kind")
            normalized.append(
                json.dumps(
                    record.model_dump(exclude_none=True),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
    except (csv.Error, ValueError) as error:
        if isinstance(error, InputValidationError):
            raise
        raise InputValidationError("INVALID_CSV", "CSV validation failed") from error
    if not normalized:
        raise InputValidationError("EMPTY_INPUT", "CSV must contain records")
    canonical = ("\n".join(normalized) + "\n").encode("utf-8")
    return canonical, validate_retrieval_jsonl(canonical, kind)
