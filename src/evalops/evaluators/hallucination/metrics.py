"""Response-level hallucination metrics, confusion matrices, and slices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


class ConfusionMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)


class HallucinationMetricsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confusion_matrix: ConfusionMatrix
    metrics: dict[str, float]
    false_positive_ids: list[str] = Field(default_factory=list)
    false_negative_ids: list[str] = Field(default_factory=list)
    slices: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _metrics(matrix: ConfusionMatrix) -> dict[str, float]:
    total = matrix.tp + matrix.tn + matrix.fp + matrix.fn
    precision = _safe_ratio(matrix.tp, matrix.tp + matrix.fp)
    recall = _safe_ratio(matrix.tp, matrix.tp + matrix.fn)
    specificity = _safe_ratio(matrix.tn, matrix.tn + matrix.fp)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": _safe_ratio(matrix.tp + matrix.tn, total),
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "false_positive_rate": _safe_ratio(matrix.fp, matrix.fp + matrix.tn),
        "false_negative_rate": _safe_ratio(matrix.fn, matrix.fn + matrix.tp),
    }


def _build_report(
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Sequence[HallucinationPrediction],
) -> tuple[ConfusionMatrix, dict[str, float], list[str], list[str]]:
    if len({prediction.example_id for prediction in predictions}) != len(predictions):
        raise ValueError("duplicate prediction example ID")
    prediction_map = {prediction.example_id: prediction for prediction in predictions}
    if set(prediction_map) != set(ground_truth):
        raise ValueError("ground truth and prediction IDs must match exactly")
    tp = tn = fp = fn = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    for example_id in ground_truth:
        actual = ground_truth[example_id] is HallucinationLabel.HALLUCINATED
        predicted = prediction_map[example_id].label is HallucinationLabel.HALLUCINATED
        if actual and predicted:
            tp += 1
        elif not actual and not predicted:
            tn += 1
        elif not actual and predicted:
            fp += 1
            false_positive_ids.append(example_id)
        else:
            fn += 1
            false_negative_ids.append(example_id)
    matrix = ConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn)
    return matrix, _metrics(matrix), false_positive_ids, false_negative_ids


def evaluate_hallucination_predictions(
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Sequence[HallucinationPrediction],
    *,
    metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> HallucinationMetricsReport:
    """Evaluate response labels and optionally calculate task/model slices."""

    matrix, metrics, false_positive_ids, false_negative_ids = _build_report(
        ground_truth, predictions
    )
    slices: dict[str, dict[str, dict[str, float]]] = {}
    if metadata is not None:
        for dimension in ("task_type", "model"):
            values = sorted(
                {str(metadata[example_id].get(dimension, "unknown")) for example_id in ground_truth}
            )
            dimension_slices: dict[str, dict[str, float]] = {}
            for value in values:
                ids = [
                    example_id
                    for example_id in ground_truth
                    if str(metadata[example_id].get(dimension, "unknown")) == value
                ]
                sub_ground_truth = {example_id: ground_truth[example_id] for example_id in ids}
                sub_predictions = [
                    prediction for prediction in predictions if prediction.example_id in ids
                ]
                _, sub_metrics, _, _ = _build_report(sub_ground_truth, sub_predictions)
                dimension_slices[value] = sub_metrics
            slices[dimension] = dimension_slices
    return HallucinationMetricsReport(
        confusion_matrix=matrix,
        metrics=metrics,
        false_positive_ids=false_positive_ids,
        false_negative_ids=false_negative_ids,
        slices=slices,
    )
