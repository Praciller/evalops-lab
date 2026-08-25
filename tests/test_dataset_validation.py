from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.datasets.validation import load_rag_cases, validate_rag_cases


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "THQA-001",
        "question": "กรุงเทพมหานครเป็นเมืองหลวงของประเทศใด",
        "ground_truth": "ประเทศไทย",
        "relevant_document_ids": ["doc-1"],
        "acceptable_answers": ["ไทย", "ประเทศไทย"],
        "category": "direct_factual",
        "difficulty": "easy",
        "requires_abstention": False,
        "metadata": {"source": "fixture"},
    }
    record.update(overrides)
    return record


def test_valid_case_and_abstention_case_are_accepted() -> None:
    report = validate_rag_cases(
        [
            _record(),
            _record(
                id="THQA-002",
                question="ข้อมูลที่ให้มาระบุอายุของผู้เขียนหรือไม่",
                requires_abstention=True,
                relevant_document_ids=[],
            ),
        ],
        document_ids={"doc-1"},
    )

    assert report.valid
    assert report.records_checked == 2
    assert report.issues == []


def test_duplicate_ids_are_reported() -> None:
    report = validate_rag_cases([_record(), _record()], document_ids={"doc-1"})

    assert not report.valid
    assert any(issue.code == "DUPLICATE_ID" for issue in report.issues)


def test_invalid_category_is_reported_as_a_schema_error() -> None:
    report = validate_rag_cases([_record(category="made_up")], document_ids={"doc-1"})

    assert not report.valid
    assert any(issue.code == "INVALID_CATEGORY" for issue in report.issues)


def test_empty_ground_truth_is_rejected_unless_it_is_a_clear_abstention_label() -> None:
    report = validate_rag_cases([_record(ground_truth="")], document_ids={"doc-1"})
    abstention_report = validate_rag_cases(
        [
            _record(
                ground_truth="Insufficient information.",
                requires_abstention=True,
                relevant_document_ids=[],
            )
        ],
        document_ids={"doc-1"},
    )

    assert not report.valid
    assert any(issue.code == "EMPTY_GROUND_TRUTH" for issue in report.issues)
    assert abstention_report.valid


def test_unknown_relevant_document_is_reported() -> None:
    report = validate_rag_cases(
        [_record(relevant_document_ids=["missing-doc"])], document_ids={"doc-1"}
    )

    assert not report.valid
    assert any(issue.code == "UNKNOWN_DOCUMENT" for issue in report.issues)


def test_near_duplicate_questions_are_reported() -> None:
    second = _record(
        id="THQA-002",
        question="กรุงเทพมหานคร เป็นเมืองหลวงของประเทศใด?",
    )

    report = validate_rag_cases([_record(), second], document_ids={"doc-1"})

    assert not report.valid
    assert any(issue.code == "NEAR_DUPLICATE_QUESTION" for issue in report.issues)


def test_jsonl_loader_reports_the_line_that_cannot_be_parsed(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_record(), ensure_ascii=False) + "\n{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        load_rag_cases(path)
