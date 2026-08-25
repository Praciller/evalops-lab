from __future__ import annotations

import pytest

from evalops.evaluators.hallucination.comparison import (
    compare_hallucination_predictions,
    exact_mcnemar,
)
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


def _prediction(example_id: str, label: HallucinationLabel) -> HallucinationPrediction:
    return HallucinationPrediction(example_id=example_id, label=label)


def test_paired_comparison_persists_correctness_categories_and_transitions() -> None:
    ground_truth = {
        "both": HallucinationLabel.GROUNDED,
        "heuristic": HallucinationLabel.GROUNDED,
        "hhem": HallucinationLabel.HALLUCINATED,
        "wrong": HallucinationLabel.HALLUCINATED,
    }
    heuristic = {
        "both": _prediction("both", HallucinationLabel.GROUNDED),
        "heuristic": _prediction("heuristic", HallucinationLabel.GROUNDED),
        "hhem": _prediction("hhem", HallucinationLabel.GROUNDED),
        "wrong": _prediction("wrong", HallucinationLabel.GROUNDED),
    }
    candidate = {
        "both": _prediction("both", HallucinationLabel.GROUNDED),
        "heuristic": _prediction("heuristic", HallucinationLabel.HALLUCINATED),
        "hhem": _prediction("hhem", HallucinationLabel.HALLUCINATED),
        "wrong": _prediction("wrong", HallucinationLabel.GROUNDED),
    }

    report = compare_hallucination_predictions(ground_truth, heuristic, candidate)

    assert report.categories == {
        "BOTH_CORRECT": ["both"],
        "HEURISTIC_ONLY_CORRECT": ["heuristic"],
        "HHEM_ONLY_CORRECT": ["hhem"],
        "BOTH_WRONG": ["wrong"],
    }
    assert report.heuristic_fn_hhem_correct == ["hhem"]
    assert report.heuristic_correct_hhem_fp == ["heuristic"]
    assert report.mcnemar.heuristic_correct_candidate_wrong == 1
    assert report.mcnemar.heuristic_wrong_candidate_correct == 1
    assert report.mcnemar.p_value == 1.0


def test_paired_comparison_rejects_mismatched_ids() -> None:
    with pytest.raises(ValueError, match="identical example IDs"):
        compare_hallucination_predictions(
            {"a": HallucinationLabel.GROUNDED},
            {"a": _prediction("a", HallucinationLabel.GROUNDED)},
            {"b": _prediction("b", HallucinationLabel.GROUNDED)},
        )


def test_exact_mcnemar_handles_no_discordant_pairs() -> None:
    result = exact_mcnemar([True, True], [True, True])

    assert result.statistic == 0.0
    assert result.p_value == 1.0
