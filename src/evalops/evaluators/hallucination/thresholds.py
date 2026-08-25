"""Score-threshold analysis with an explicit validation-only selection guard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evalops.evaluators.hallucination.metrics import ConfusionMatrix, _metrics
from evalops.models.hallucination import HallucinationLabel


class ThresholdSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float = Field(ge=0.0, le=1.0)
    threshold_source: str
    validation_split: str
    selection_metric: str
    random_seed: int
    candidates: list[float]


def _threshold_metrics(
    support_scores: Mapping[str, float],
    ground_truth: Mapping[str, HallucinationLabel],
    threshold: float,
) -> dict[str, float]:
    if set(support_scores) != set(ground_truth):
        raise ValueError("support score and ground-truth IDs must match exactly")
    tp = tn = fp = fn = 0
    for example_id, support_score in support_scores.items():
        predicted_hallucinated = support_score < threshold
        actual_hallucinated = ground_truth[example_id] is HallucinationLabel.HALLUCINATED
        if actual_hallucinated and predicted_hallucinated:
            tp += 1
        elif not actual_hallucinated and not predicted_hallucinated:
            tn += 1
        elif not actual_hallucinated:
            fp += 1
        else:
            fn += 1
    return _metrics(ConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn))


def analyze_thresholds(
    support_scores: Mapping[str, float],
    ground_truth: Mapping[str, HallucinationLabel],
    thresholds: Sequence[float],
) -> list[dict[str, Any]]:
    """Return a deterministic precision/recall tradeoff table for supplied data."""

    if not thresholds:
        raise ValueError("at least one threshold is required")
    normalized = sorted(set(float(threshold) for threshold in thresholds))
    if any(not 0.0 <= threshold <= 1.0 for threshold in normalized):
        raise ValueError("thresholds must be between 0 and 1")
    return [
        {"threshold": threshold, **_threshold_metrics(support_scores, ground_truth, threshold)}
        for threshold in normalized
    ]


def select_threshold_from_validation(
    support_scores: Mapping[str, float],
    ground_truth: Mapping[str, HallucinationLabel],
    *,
    validation_split: str,
    candidates: Sequence[float],
    selection_metric: str = "f1",
    random_seed: int = 0,
) -> ThresholdSelection:
    """Select a threshold only when the caller explicitly supplies validation data."""

    if validation_split.casefold() == "test":
        raise ValueError("threshold selection from the official test split is forbidden")
    table = analyze_thresholds(support_scores, ground_truth, candidates)
    if selection_metric not in table[0]:
        raise ValueError(f"unknown threshold selection metric: {selection_metric}")
    best_value = max(row[selection_metric] for row in table)
    best_threshold = min(row["threshold"] for row in table if row[selection_metric] == best_value)
    return ThresholdSelection(
        threshold=best_threshold,
        threshold_source="validation-derived",
        validation_split=validation_split,
        selection_metric=selection_metric,
        random_seed=random_seed,
        candidates=[row["threshold"] for row in table],
    )
