"""Phase 6.3 Task 5: deterministic, evaluator-owned per-query transitions."""

from __future__ import annotations

from copy import deepcopy

import pytest

from evalops.failures.taxonomy import FailureCategory
from evalops.models.runs import EvaluationResult, RunConfig
from evalops.runners.retrieval import run_retrieval_evaluation
from evalops.workspace.comparison.failures import build_failure_transitions
from evalops.workspace.comparison.models import FailureTransition

TRUTH = {key: [f"doc-{key}"] for key in ("a", "b", "c", "d", "e")}


def _result(predictions: dict[str, list[str]]) -> EvaluationResult:
    return run_retrieval_evaluation(
        TRUTH,
        predictions,
        RunConfig(
            run_id="test",
            dataset_name="synthetic",
            dataset_version="v1",
            system_name="fixture",
            top_k=1,
        ),
    )


def test_all_failure_transition_states_preserve_original_metrics() -> None:
    baseline = _result({"a": ["doc-a"], "b": ["doc-b"], "c": ["bad"], "d": ["bad"], "e": ["bad"]})
    candidate = _result({"a": ["doc-a"], "b": ["bad"], "c": ["doc-c"], "d": ["bad"], "e": ["bad"]})
    original = deepcopy(candidate.details)
    # Simulate a separate evaluator-owned failure classification for query e.
    # The transition builder must never infer the label from metric values.
    candidate.details["per_query"]["e"].failure_category = FailureCategory.SHOULD_ABSTAIN
    expected = {
        "a": FailureTransition.UNCHANGED_PASS,
        "b": FailureTransition.REGRESSED,
        "c": FailureTransition.IMPROVED,
        "d": FailureTransition.PERSISTENT_FAILURE,
        "e": FailureTransition.CHANGED_FAILURE,
    }
    transitions = build_failure_transitions(baseline, candidate)
    assert [item.query_id for item in transitions] == sorted(expected)
    assert {item.query_id: item.transition for item in transitions} == expected
    for item in transitions:
        assert item.baseline_metrics == baseline.details["per_query"][item.query_id].metrics
        assert item.candidate_metrics == candidate.details["per_query"][item.query_id].metrics
    assert candidate.details["per_query"]["a"].metrics == original["per_query"]["a"].metrics


def test_no_private_classification_evidence_is_copied() -> None:
    baseline = _result({"a": ["bad"]})
    candidate = _result({"a": ["doc-a"]})
    records = build_failure_transitions(baseline, candidate)
    assert records[0].transition == FailureTransition.IMPROVED
    assert "relevant_document_ids" not in records[0].model_dump_json()
    assert records[0].baseline_category == FailureCategory.RETRIEVAL_MISS


@pytest.mark.parametrize("alter", ["missing", "extra", "absent", "invalid"])
def test_missing_or_malformed_query_evidence_fails_closed(alter: str) -> None:
    baseline = _result({"a": ["bad"]})
    candidate = _result({"a": ["doc-a"]})
    if alter == "missing":
        del candidate.details["per_query"]["a"]
    elif alter == "extra":
        candidate.details["per_query"]["extra"] = candidate.details["per_query"]["a"]
    elif alter == "absent":
        del candidate.details["per_query"]
    else:
        candidate.details["per_query"]["a"] = {"failure_category": "UNKNOWN"}
    with pytest.raises(ValueError):
        build_failure_transitions(baseline, candidate)


def test_nonretrieval_result_rejected_even_if_query_data_is_present() -> None:
    baseline = _result({"a": ["bad"]})
    candidate = _result({"a": ["doc-a"]})
    candidate.evaluation_type = "generation"
    with pytest.raises(ValueError, match="retrieval"):
        build_failure_transitions(baseline, candidate)
