"""Contract tests for the explicit synthetic Thai Support RAG EvalOps adapter."""

from __future__ import annotations

import copy
import json

import pytest

from scripts.import_synthetic_thai_support import _write_jsonl, convert


@pytest.fixture
def report() -> dict:
    return {
        "dataset_id": "synthetic-thai-enterprise-policy-v1",
        "mode": "offline_character_bigram_lexical_baseline",
        "case_count": 2,
        "permission_safe_cases": 2,
        "cases": [
            {
                "case_id": "q-refund",
                "expected_ids": ["th-public-refund"],
                "retrieved_ids": ["th-public-refund"],
                "expected_abstain": False,
                "injection": False,
                "permission_safe": True,
            },
            {
                "case_id": "q-injection",
                "expected_ids": [],
                "retrieved_ids": [],
                "expected_abstain": True,
                "injection": True,
                "permission_safe": True,
            },
        ],
    }


def test_converter_keeps_only_retrieval_contract_and_synthetic_label(
    report: dict, tmp_path
) -> None:
    ground_truth, predictions, metadata = convert(report)
    assert ground_truth == [
        {"query_id": "q-refund", "relevant_document_ids": ["th-public-refund"]},
        {"query_id": "q-injection", "relevant_document_ids": []},
    ]
    assert predictions[0]["retrieved_document_ids"] == ["th-public-refund"]
    assert predictions[1]["retrieved_document_ids"] == []
    assert metadata["data_kind"] == "SYNTHETIC_FIXTURE"
    assert metadata["claim_scope"] == "INTEGRATION_ONLY"
    assert (metadata["case_count"], metadata["abstention_cases"], metadata["injection_cases"]) == (
        2,
        1,
        1,
    )

    path = tmp_path / "predictions.jsonl"
    _write_jsonl(path, predictions)
    assert [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ] == predictions
    assert all(set(row) <= {"query_id", "retrieved_document_ids"} for row in predictions)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", "non-public-sensitive-corpus"),
        ("mode", "live-production"),
        ("case_count", 3),
        ("permission_safe_cases", 1),
    ],
)
def test_rejects_wrong_provenance_or_counts(report: dict, field: str, value) -> None:
    report[field] = value
    with pytest.raises(ValueError):
        convert(report)


def test_rejects_unsafe_or_duplicate_cases(report: dict) -> None:
    unsafe = copy.deepcopy(report)
    unsafe["cases"][0]["permission_safe"] = False
    with pytest.raises(ValueError):
        convert(unsafe)

    duplicate = copy.deepcopy(report)
    duplicate["cases"][1]["case_id"] = duplicate["cases"][0]["case_id"]
    with pytest.raises(ValueError):
        convert(duplicate)

    invalid_id = copy.deepcopy(report)
    invalid_id["cases"][0]["retrieved_ids"] = ["safe", "safe"]
    with pytest.raises(ValueError):
        convert(invalid_id)

    invalid_abstain = copy.deepcopy(report)
    invalid_abstain["cases"][1]["expected_ids"] = ["forbidden"]
    with pytest.raises(ValueError):
        convert(invalid_abstain)
