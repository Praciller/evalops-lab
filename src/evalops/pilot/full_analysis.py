"""Deterministic analysis helpers for a complete local judge run."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any

from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction

METRIC_NAMES = (
    "precision",
    "recall",
    "f1",
    "accuracy",
    "specificity",
    "balanced_accuracy",
    "false_positive_rate",
    "false_negative_rate",
)


def _metric_report(
    example_ids: Sequence[str],
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
) -> dict[str, Any]:
    selected_ground_truth = {example_id: ground_truth[example_id] for example_id in example_ids}
    selected_predictions = [predictions[example_id] for example_id in example_ids]
    report = evaluate_hallucination_predictions(selected_ground_truth, selected_predictions)
    return {
        "total": len(example_ids),
        "confusion_matrix": report.confusion_matrix.model_dump(mode="json"),
        "metrics": report.metrics,
        "false_positive_ids": report.false_positive_ids,
        "false_negative_ids": report.false_negative_ids,
    }


def _rank_quartiles(
    example_ids: Sequence[str], values: Mapping[str, int]
) -> tuple[dict[str, list[str]], dict[str, dict[str, int | None]]]:
    ordered = sorted(example_ids, key=lambda example_id: (values[example_id], example_id))
    buckets: dict[str, list[str]] = {f"Q{index}": [] for index in range(1, 5)}
    for rank, example_id in enumerate(ordered):
        bucket = min(3, rank * 4 // len(ordered))
        buckets[f"Q{bucket + 1}"].append(example_id)
    ranges = {
        bucket: {
            "min": min((values[example_id] for example_id in bucket_ids), default=None),
            "max": max((values[example_id] for example_id in bucket_ids), default=None),
        }
        for bucket, bucket_ids in buckets.items()
    }
    return buckets, ranges


def _slice_reports(
    groups: Mapping[str, Sequence[str]],
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
) -> dict[str, dict[str, Any]]:
    return {
        name: _metric_report(example_ids, ground_truth, predictions)
        for name, example_ids in groups.items()
    }


def _dimension_groups(
    example_ids: Sequence[str], metadata: Mapping[str, Mapping[str, Any]], dimension: str
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for example_id in example_ids:
        value = str(metadata.get(example_id, {}).get(dimension, "unknown"))
        groups.setdefault(value, []).append(example_id)
    return dict(sorted(groups.items()))


def _calibration(
    example_ids: Sequence[str],
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
    confidence: Mapping[str, float] | None,
) -> dict[str, Any]:
    targets = [
        1.0 if ground_truth[example_id] is HallucinationLabel.HALLUCINATED else 0.0
        for example_id in example_ids
    ]
    probabilities = [predictions[example_id].score for example_id in example_ids]
    probability_bins = [
        {
            "count": 0,
            "mean_prediction": 0.0,
            "mean_target": 0.0,
            "absolute_gap": 0.0,
        }
        for _ in range(10)
    ]
    for probability, target in zip(probabilities, targets, strict=True):
        index = min(9, max(0, math.floor(probability * 10)))
        bin_value = probability_bins[index]
        bin_value["count"] += 1
        bin_value["mean_prediction"] += probability
        bin_value["mean_target"] += target
    for bin_value in probability_bins:
        count = int(bin_value["count"])
        if count:
            bin_value["mean_prediction"] /= count
            bin_value["mean_target"] /= count
            bin_value["absolute_gap"] = abs(bin_value["mean_prediction"] - bin_value["mean_target"])
    probability_ece = sum(
        (bin_value["count"] / len(example_ids)) * bin_value["absolute_gap"]
        for bin_value in probability_bins
    )
    result: dict[str, Any] = {
        "sample_count": len(example_ids),
        "hallucination_probability": {
            "brier_score": fmean(
                (probability - target) ** 2
                for probability, target in zip(probabilities, targets, strict=True)
            ),
            "ece_10_bins": probability_ece,
            "binning": "fixed-width [0,1] bins; final bin includes 1.0",
            "bins": probability_bins,
        },
    }
    if confidence is not None:
        confidence_values = [confidence[example_id] for example_id in example_ids]
        correctness = [
            float(predictions[example_id].label is ground_truth[example_id])
            for example_id in example_ids
        ]
        confidence_bins = [
            {"count": 0, "mean_confidence": 0.0, "mean_correct": 0.0, "absolute_gap": 0.0}
            for _ in range(10)
        ]
        for value, correct in zip(confidence_values, correctness, strict=True):
            index = min(9, max(0, math.floor(value * 10)))
            bin_value = confidence_bins[index]
            bin_value["count"] += 1
            bin_value["mean_confidence"] += value
            bin_value["mean_correct"] += correct
        for bin_value in confidence_bins:
            count = int(bin_value["count"])
            if count:
                bin_value["mean_confidence"] /= count
                bin_value["mean_correct"] /= count
                bin_value["absolute_gap"] = abs(
                    bin_value["mean_confidence"] - bin_value["mean_correct"]
                )
        result["decision_confidence"] = {
            "brier_score": fmean(
                (value - correct) ** 2
                for value, correct in zip(confidence_values, correctness, strict=True)
            ),
            "ece_10_bins": sum(
                (bin_value["count"] / len(example_ids)) * bin_value["absolute_gap"]
                for bin_value in confidence_bins
            ),
            "calibration_target": "whether the predicted label equals the human label",
            "binning": "fixed-width [0,1] bins; final bin includes 1.0",
            "bins": confidence_bins,
        }
    return result


def _error_analysis(
    example_ids: Sequence[str],
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
    metadata: Mapping[str, Mapping[str, Any]],
    confidence: Mapping[str, float] | None,
) -> dict[str, Any]:
    false_positive_ids = [
        example_id
        for example_id in example_ids
        if ground_truth[example_id] is HallucinationLabel.GROUNDED
        and predictions[example_id].label is HallucinationLabel.HALLUCINATED
    ]
    false_negative_ids = [
        example_id
        for example_id in example_ids
        if ground_truth[example_id] is HallucinationLabel.HALLUCINATED
        and predictions[example_id].label is HallucinationLabel.GROUNDED
    ]
    error_ids = false_positive_ids + false_negative_ids
    by_task = Counter(
        str(metadata.get(example_id, {}).get("task_type", "unknown")) for example_id in error_ids
    )
    by_model = Counter(
        str(metadata.get(example_id, {}).get("model", "unknown")) for example_id in error_ids
    )
    error_confidences = [confidence[example_id] for example_id in error_ids] if confidence else []
    return {
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
        "error_count": len(error_ids),
        "errors_by_task_type": dict(sorted(by_task.items())),
        "errors_by_source_model": dict(sorted(by_model.items())),
        "mean_error_confidence": fmean(error_confidences) if error_confidences else None,
        "raw_context_persisted": False,
    }


def summarize_full_predictions(
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
    metadata: Mapping[str, Mapping[str, Any]],
    lengths: Mapping[str, Mapping[str, int]],
    *,
    confidence: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Summarize a complete, exact-ID local run without mutating labels."""

    expected = set(ground_truth)
    if set(predictions) != expected:
        raise ValueError("full prediction summary requires identical example IDs")
    if set(lengths) != expected:
        raise ValueError("full length summary requires identical example IDs")
    if confidence is not None and set(confidence) != expected:
        raise ValueError("full confidence summary requires identical example IDs")
    example_ids = list(ground_truth)
    report = _metric_report(example_ids, ground_truth, predictions)
    task_groups = _dimension_groups(example_ids, metadata, "task_type")
    model_groups = _dimension_groups(example_ids, metadata, "model")
    response_groups, response_ranges = _rank_quartiles(
        example_ids,
        {example_id: lengths[example_id]["response_chars"] for example_id in example_ids},
    )
    context_groups, context_ranges = _rank_quartiles(
        example_ids,
        {example_id: lengths[example_id]["source_context_chars"] for example_id in example_ids},
    )
    return {
        "example_count": len(example_ids),
        "confusion_matrix": report["confusion_matrix"],
        "metrics": report["metrics"],
        "false_positive_ids": report["false_positive_ids"],
        "false_negative_ids": report["false_negative_ids"],
        "task_slices": _slice_reports(task_groups, ground_truth, predictions),
        "source_model_slices": _slice_reports(model_groups, ground_truth, predictions),
        "length_slices": {
            "response_chars": {
                "method": "deterministic rank quartiles sorted by length then example_id",
                "ranges": response_ranges,
                "slices": _slice_reports(response_groups, ground_truth, predictions),
            },
            "source_context_chars": {
                "method": "deterministic rank quartiles sorted by length then example_id",
                "ranges": context_ranges,
                "slices": _slice_reports(context_groups, ground_truth, predictions),
            },
        },
        "calibration": _calibration(example_ids, ground_truth, predictions, confidence),
        "error_analysis": _error_analysis(
            example_ids, ground_truth, predictions, metadata, confidence
        ),
    }


def _bootstrap_metric(
    example_ids: Sequence[str],
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, HallucinationPrediction],
    metric_name: str,
) -> float:
    # The metric layer intentionally rejects duplicate IDs; a bootstrap sample
    # with replacement needs occurrence-local IDs while preserving labels.
    sampled_ground_truth = {
        f"{example_id}#bootstrap-{index}": ground_truth[example_id]
        for index, example_id in enumerate(example_ids)
    }
    sampled_predictions = {
        f"{example_id}#bootstrap-{index}": predictions[example_id].model_copy(
            update={"example_id": f"{example_id}#bootstrap-{index}"}
        )
        for index, example_id in enumerate(example_ids)
    }
    report = evaluate_hallucination_predictions(
        sampled_ground_truth, list(sampled_predictions.values())
    )
    return float(report.metrics[metric_name])


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def bootstrap_confidence_intervals(
    example_ids: Sequence[str],
    ground_truth: Mapping[str, HallucinationLabel],
    local_predictions: Mapping[str, HallucinationPrediction],
    hhem_predictions: Mapping[str, HallucinationPrediction],
    *,
    seed: int,
    replicates: int = 10_000,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Calculate reproducible IID example bootstrap intervals and paired deltas."""

    if not example_ids:
        raise ValueError("bootstrap requires at least one example")
    if replicates < 1:
        raise ValueError("bootstrap requires at least one replicate")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")
    expected = set(example_ids)
    if (
        set(ground_truth) != expected
        or set(local_predictions) != expected
        or set(hhem_predictions) != expected
    ):
        raise ValueError("bootstrap inputs require identical example IDs")
    rng = random.Random(seed)
    local_values: dict[str, list[float]] = {
        name: [] for name in ("f1", "balanced_accuracy", "recall", "false_positive_rate")
    }
    delta_values: dict[str, list[float]] = {name: [] for name in local_values}
    for _ in range(replicates):
        sample = [example_ids[rng.randrange(len(example_ids))] for _ in example_ids]
        for name in local_values:
            local_value = _bootstrap_metric(sample, ground_truth, local_predictions, name)
            hhem_value = _bootstrap_metric(sample, ground_truth, hhem_predictions, name)
            local_values[name].append(local_value)
            delta_values[name].append(local_value - hhem_value)
    alpha = (1.0 - confidence_level) / 2.0
    return {
        "method": "iid-example-bootstrap",
        "seed": seed,
        "replicates": replicates,
        "confidence_level": confidence_level,
        "local_metric_intervals": {
            name: {
                "estimate": _bootstrap_metric(example_ids, ground_truth, local_predictions, name),
                "lower": _percentile(values, alpha),
                "upper": _percentile(values, 1.0 - alpha),
            }
            for name, values in local_values.items()
        },
        "local_minus_hhem_delta_intervals": {
            name: {
                "estimate": _bootstrap_metric(example_ids, ground_truth, local_predictions, name)
                - _bootstrap_metric(example_ids, ground_truth, hhem_predictions, name),
                "lower": _percentile(values, alpha),
                "upper": _percentile(values, 1.0 - alpha),
            }
            for name, values in delta_values.items()
        },
    }
