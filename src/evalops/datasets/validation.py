"""Validation of local RAG benchmark records."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalops.models.datasets import (
    DatasetValidationIssue,
    DatasetValidationReport,
    RAGCase,
)


def _normalize_question(question: str) -> str:
    """Normalize enough punctuation/spacing to detect obvious near duplicates."""

    return re.sub(r"[^\w\u0e00-\u0e7f]+", "", question.casefold())


def _validation_code(error: Mapping[str, Any]) -> str:
    location = error.get("loc", ())
    field = location[0] if location else "record"
    if field == "category":
        return "INVALID_CATEGORY"
    if field == "ground_truth" and error.get("type") == "string_too_short":
        return "EMPTY_GROUND_TRUTH"
    if error.get("type") == "missing":
        return "MISSING_REQUIRED_FIELD"
    return "INVALID_FIELD"


def _parse_case(
    record: RAGCase | Mapping[str, Any], index: int
) -> tuple[RAGCase | None, list[DatasetValidationIssue]]:
    if isinstance(record, RAGCase):
        return record, []

    try:
        return RAGCase.model_validate(record), []
    except ValidationError as error:
        issues = [
            DatasetValidationIssue(
                code=_validation_code(detail),
                message=detail.get("msg", "invalid record"),
                record_id=str(record.get("id", f"line-{index}")),
            )
            for detail in error.errors()
        ]
        return None, issues


def validate_rag_cases(
    records: Sequence[RAGCase | Mapping[str, Any]],
    *,
    document_ids: set[str] | None = None,
    near_duplicate_threshold: float = 0.95,
) -> DatasetValidationReport:
    """Validate records without mutating them or silently repairing labels."""

    issues: list[DatasetValidationIssue] = []
    parsed_cases: list[RAGCase] = []
    seen_ids: set[str] = set()

    for index, record in enumerate(records, start=1):
        case, parse_issues = _parse_case(record, index)
        issues.extend(parse_issues)
        if case is None:
            continue
        if case.id in seen_ids:
            issues.append(
                DatasetValidationIssue(
                    code="DUPLICATE_ID",
                    message=f"case ID '{case.id}' occurs more than once",
                    record_id=case.id,
                )
            )
        seen_ids.add(case.id)
        parsed_cases.append(case)

        if document_ids is not None:
            unknown_documents = sorted(set(case.relevant_document_ids) - document_ids)
            if unknown_documents:
                issues.append(
                    DatasetValidationIssue(
                        code="UNKNOWN_DOCUMENT",
                        message=f"unknown relevant document IDs: {', '.join(unknown_documents)}",
                        record_id=case.id,
                    )
                )

    for left_index, left in enumerate(parsed_cases):
        left_question = _normalize_question(left.question)
        if not left_question:
            continue
        for right in parsed_cases[left_index + 1 :]:
            right_question = _normalize_question(right.question)
            if (
                SequenceMatcher(None, left_question, right_question).ratio()
                >= near_duplicate_threshold
            ):
                issues.append(
                    DatasetValidationIssue(
                        code="NEAR_DUPLICATE_QUESTION",
                        message=f"question is very similar to case '{left.id}'",
                        record_id=right.id,
                    )
                )

    return DatasetValidationReport(
        valid=not issues,
        records_checked=len(records),
        issues=issues,
    )


def load_rag_cases(path: str | Path) -> list[RAGCase]:
    """Load and parse a UTF-8 JSONL file, preserving line context on errors."""

    cases: list[RAGCase] = []
    file_path = Path(path)
    with file_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                cases.append(RAGCase.model_validate(record))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
                raise ValueError(
                    f"could not parse {file_path} line {line_number}: {error}"
                ) from error
    return cases
