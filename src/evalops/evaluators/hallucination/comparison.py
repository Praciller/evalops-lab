"""Paired evaluator comparison and lightweight exact McNemar statistics."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


class McNemarResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heuristic_correct_candidate_wrong: int = Field(ge=0)
    heuristic_wrong_candidate_correct: int = Field(ge=0)
    statistic: float = Field(ge=0.0)
    p_value: float = Field(ge=0.0, le=1.0)
    method: str = "exact-two-sided-binomial"


class PairedComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_count: int = Field(ge=0)
    categories: dict[str, list[str]]
    heuristic_fn_hhem_correct: list[str] = Field(default_factory=list)
    heuristic_fp_hhem_correct: list[str] = Field(default_factory=list)
    heuristic_correct_hhem_fn: list[str] = Field(default_factory=list)
    heuristic_correct_hhem_fp: list[str] = Field(default_factory=list)
    hhem_false_positive_ids: list[str] = Field(default_factory=list)
    hhem_false_negative_ids: list[str] = Field(default_factory=list)
    mcnemar: McNemarResult


def _is_correct(actual: HallucinationLabel, predicted: HallucinationLabel) -> bool:
    return actual is predicted


def exact_mcnemar(heuristic_correct: list[bool], candidate_correct: list[bool]) -> McNemarResult:
    if len(heuristic_correct) != len(candidate_correct):
        raise ValueError("McNemar inputs must have equal length")
    b = sum(h and not c for h, c in zip(heuristic_correct, candidate_correct, strict=True))
    c = sum(not h and c for h, c in zip(heuristic_correct, candidate_correct, strict=True))
    discordant = b + c
    statistic = ((abs(b - c) - 1) ** 2 / discordant) if discordant else 0.0
    tail = sum(math.comb(discordant, index) for index in range(min(b, c) + 1))
    p_value = min(1.0, 2.0 * tail / (2**discordant)) if discordant else 1.0
    return McNemarResult(
        heuristic_correct_candidate_wrong=b,
        heuristic_wrong_candidate_correct=c,
        statistic=statistic,
        p_value=p_value,
    )


def compare_hallucination_predictions(
    ground_truth: Mapping[str, HallucinationLabel],
    heuristic: Mapping[str, HallucinationPrediction],
    candidate: Mapping[str, HallucinationPrediction],
) -> PairedComparisonReport:
    """Compare two predictions on exactly the same human-labeled example IDs."""

    expected_ids = set(ground_truth)
    if set(heuristic) != expected_ids or set(candidate) != expected_ids:
        raise ValueError("paired comparison requires identical example IDs")
    categories: dict[str, list[str]] = {
        "BOTH_CORRECT": [],
        "HEURISTIC_ONLY_CORRECT": [],
        "HHEM_ONLY_CORRECT": [],
        "BOTH_WRONG": [],
    }
    heuristic_fn_hhem_correct: list[str] = []
    heuristic_fp_hhem_correct: list[str] = []
    heuristic_correct_hhem_fn: list[str] = []
    heuristic_correct_hhem_fp: list[str] = []
    hhem_false_positive_ids: list[str] = []
    hhem_false_negative_ids: list[str] = []
    heuristic_correctness: list[bool] = []
    candidate_correctness: list[bool] = []
    for example_id in ground_truth:
        actual = ground_truth[example_id]
        heuristic_prediction = heuristic[example_id].label
        candidate_prediction = candidate[example_id].label
        heuristic_is_correct = _is_correct(actual, heuristic_prediction)
        candidate_is_correct = _is_correct(actual, candidate_prediction)
        heuristic_correctness.append(heuristic_is_correct)
        candidate_correctness.append(candidate_is_correct)
        if heuristic_is_correct and candidate_is_correct:
            categories["BOTH_CORRECT"].append(example_id)
        elif heuristic_is_correct:
            categories["HEURISTIC_ONLY_CORRECT"].append(example_id)
        elif candidate_is_correct:
            categories["HHEM_ONLY_CORRECT"].append(example_id)
        else:
            categories["BOTH_WRONG"].append(example_id)
        heuristic_fn = (
            actual is HallucinationLabel.HALLUCINATED
            and heuristic_prediction is HallucinationLabel.GROUNDED
        )
        heuristic_fp = (
            actual is HallucinationLabel.GROUNDED
            and heuristic_prediction is HallucinationLabel.HALLUCINATED
        )
        candidate_fn = (
            actual is HallucinationLabel.HALLUCINATED
            and candidate_prediction is HallucinationLabel.GROUNDED
        )
        candidate_fp = (
            actual is HallucinationLabel.GROUNDED
            and candidate_prediction is HallucinationLabel.HALLUCINATED
        )
        if heuristic_fn:
            if candidate_is_correct:
                heuristic_fn_hhem_correct.append(example_id)
        if heuristic_fp:
            if candidate_is_correct:
                heuristic_fp_hhem_correct.append(example_id)
        if heuristic_is_correct and candidate_fn:
            heuristic_correct_hhem_fn.append(example_id)
        if heuristic_is_correct and candidate_fp:
            heuristic_correct_hhem_fp.append(example_id)
        if candidate_fp:
            hhem_false_positive_ids.append(example_id)
        if candidate_fn:
            hhem_false_negative_ids.append(example_id)
    return PairedComparisonReport(
        example_count=len(ground_truth),
        categories=categories,
        heuristic_fn_hhem_correct=heuristic_fn_hhem_correct,
        heuristic_fp_hhem_correct=heuristic_fp_hhem_correct,
        heuristic_correct_hhem_fn=heuristic_correct_hhem_fn,
        heuristic_correct_hhem_fp=heuristic_correct_hhem_fp,
        hhem_false_positive_ids=hhem_false_positive_ids,
        hhem_false_negative_ids=hhem_false_negative_ids,
        mcnemar=exact_mcnemar(heuristic_correctness, candidate_correctness),
    )


def compare_hallucination_artifacts(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two saved EvalOps artifacts without loading source text."""

    baseline_examples = baseline.get("details", {}).get("per_example", {})
    candidate_examples = candidate.get("details", {}).get("per_example", {})
    if not isinstance(baseline_examples, dict) or not isinstance(candidate_examples, dict):
        raise ValueError("hallucination artifacts must contain details.per_example")
    if set(baseline_examples) != set(candidate_examples):
        raise ValueError("hallucination artifact populations must have identical example IDs")
    ground_truth: dict[str, HallucinationLabel] = {}
    heuristic: dict[str, HallucinationPrediction] = {}
    candidate_predictions: dict[str, HallucinationPrediction] = {}
    for example_id in baseline_examples:
        baseline_record = baseline_examples[example_id]
        candidate_record = candidate_examples[example_id]
        if baseline_record["human_label"] != candidate_record["human_label"]:
            raise ValueError("human labels differ between paired hallucination artifacts")
        ground_truth[example_id] = HallucinationLabel(baseline_record["human_label"])
        heuristic[example_id] = HallucinationPrediction(
            example_id=example_id,
            label=HallucinationLabel(baseline_record["predicted_label"]),
            score=float(baseline_record.get("score", 0.0)),
            support_score=baseline_record.get("support_score"),
        )
        candidate_predictions[example_id] = HallucinationPrediction(
            example_id=example_id,
            label=HallucinationLabel(candidate_record["predicted_label"]),
            score=float(candidate_record.get("score", 0.0)),
            support_score=candidate_record.get("support_score"),
        )
    report = compare_hallucination_predictions(ground_truth, heuristic, candidate_predictions)
    baseline_metrics = baseline.get("metrics", {})
    candidate_metrics = candidate.get("metrics", {})
    metric_delta = {
        name: float(candidate_metrics[name]) - float(baseline_metrics[name])
        for name in sorted(set(baseline_metrics) & set(candidate_metrics))
    }
    return {
        "baseline_run_id": baseline.get("run", {}).get("run_id"),
        "candidate_run_id": candidate.get("run", {}).get("run_id"),
        "baseline_evaluator": baseline.get("details", {}).get("evaluator", {}).get("name"),
        "candidate_evaluator": candidate.get("details", {}).get("evaluator", {}).get("name"),
        "metric_delta": metric_delta,
        "paired_comparison": report.model_dump(mode="json"),
    }
