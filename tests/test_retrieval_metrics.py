from __future__ import annotations

import math

import pytest

from evalops.evaluators.retrieval.metrics import (
    evaluate_retrieval,
    hit_rate_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_perfect_retrieval_has_perfect_scores() -> None:
    relevant = ["d1", "d2"]
    retrieved = ["d2", "d1", "d3"]

    assert precision_at_k(relevant, retrieved, 2) == 1.0
    assert recall_at_k(relevant, retrieved, 2) == 1.0
    assert hit_rate_at_k(relevant, retrieved, 2) == 1.0
    assert mean_reciprocal_rank(relevant, retrieved) == 1.0
    assert ndcg_at_k(relevant, retrieved, 2) == 1.0


def test_partial_retrieval_matches_manually_calculated_values() -> None:
    relevant = ["d1", "d3"]
    retrieved = ["d2", "d3", "d4"]

    assert precision_at_k(relevant, retrieved, 3) == pytest.approx(1 / 3)
    assert recall_at_k(relevant, retrieved, 3) == pytest.approx(1 / 2)
    assert hit_rate_at_k(relevant, retrieved, 3) == 1.0
    assert mean_reciprocal_rank(relevant, retrieved) == pytest.approx(1 / 2)
    expected_ndcg = (1 / math.log2(3)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k(relevant, retrieved, 3) == pytest.approx(expected_ndcg)


def test_duplicate_retrieved_ids_do_not_count_as_extra_relevant_hits() -> None:
    relevant = ["d1", "d2"]
    retrieved = ["d1", "d1", "d3"]

    assert precision_at_k(relevant, retrieved, 3) == pytest.approx(1 / 3)
    assert recall_at_k(relevant, retrieved, 3) == pytest.approx(1 / 2)
    assert mean_reciprocal_rank(relevant, retrieved) == 1.0


@pytest.mark.parametrize(
    ("relevant", "retrieved"),
    [([], []), ([], ["d1"]), (["d1"], [])],
)
def test_empty_relevance_or_results_are_safe(relevant: list[str], retrieved: list[str]) -> None:
    assert precision_at_k(relevant, retrieved, 5) == 0.0
    assert recall_at_k(relevant, retrieved, 5) == 0.0
    assert hit_rate_at_k(relevant, retrieved, 5) == 0.0
    assert mean_reciprocal_rank(relevant, retrieved) == 0.0
    assert ndcg_at_k(relevant, retrieved, 5) == 0.0


def test_k_larger_than_result_count_uses_k_as_precision_denominator() -> None:
    assert precision_at_k(["d1"], ["d1"], 5) == pytest.approx(1 / 5)
    assert recall_at_k(["d1"], ["d1"], 5) == 1.0


def test_ndcg_supports_graded_relevance_when_the_ground_truth_is_a_mapping() -> None:
    relevance = {"d1": 2, "d2": 1}

    score = ndcg_at_k(relevance, ["d2", "d1"], 2)

    ideal = 3 + 1 / math.log2(3)
    observed = 1 + 3 / math.log2(3)
    assert score == pytest.approx(observed / ideal)


def test_invalid_k_is_rejected() -> None:
    with pytest.raises(ValueError, match="k must be a positive integer"):
        precision_at_k(["d1"], ["d1"], 0)
    with pytest.raises(ValueError, match="k must be a positive integer"):
        precision_at_k(["d1"], ["d1"], -1)


def test_evaluate_retrieval_returns_macro_metrics_and_per_query_failures() -> None:
    result = evaluate_retrieval(
        {"q1": ["d1"], "q2": ["d2"]},
        {"q1": ["d1"], "q2": ["d3"]},
        k=1,
    )

    assert result.metrics["precision_at_1"] == pytest.approx(0.5)
    assert result.metrics["recall_at_1"] == pytest.approx(0.5)
    assert result.metrics["mrr"] == pytest.approx(0.5)
    assert result.per_query["q2"].failure_category == "RETRIEVAL_MISS"


def test_no_relevant_documents_are_classified_as_an_abstention_case() -> None:
    result = evaluate_retrieval({"q1": []}, {"q1": ["noise"]}, k=1)

    assert result.per_query["q1"].failure_category == "SHOULD_ABSTAIN"
