"""Metrics and paired analysis for bounded Phase 5A outputs."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import combinations
from statistics import fmean
from typing import Any

from evalops.evaluators.hallucination.comparison import exact_mcnemar
from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction
from evalops.pilot.models import PilotRunRecord


def _classification_report(
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Sequence[HallucinationPrediction],
    metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not ground_truth:
        return {
            "confusion_matrix": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
            "metrics": {
                key: 0.0
                for key in (
                    "precision",
                    "recall",
                    "f1",
                    "accuracy",
                    "specificity",
                    "balanced_accuracy",
                    "false_positive_rate",
                    "false_negative_rate",
                )
            },
            "slices": {},
        }
    report = evaluate_hallucination_predictions(ground_truth, predictions, metadata=metadata)
    return report.model_dump(mode="json")


def _latency_summary(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "mean_ms": 0.0}
    ordered = sorted(values)

    def nearest_rank(percentile: float) -> float:
        index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
        return ordered[index]

    return {
        "count": len(ordered),
        "p50_ms": nearest_rank(0.50),
        "p95_ms": nearest_rank(0.95),
        "mean_ms": fmean(ordered),
    }


def _token_summary(records: Sequence[PilotRunRecord]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "provider_reported_cost": 0.0,
    }
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
        "provider_reported_cost": ("cost",),
    }
    for record in records:
        usage = record.trace.usage or {}
        for target, keys in aliases.items():
            for key in keys:
                value = usage.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    totals[target] += value
                    break
    return totals


def summarize_provider_records(
    records: Sequence[PilotRunRecord],
    ground_truth: Mapping[str, HallucinationLabel],
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize one provider while counting missing/parse/API outcomes separately."""

    providers = {record.provider for record in records}
    if len(providers) > 1:
        raise ValueError("provider summary requires records from exactly one provider")
    ids = [record.example_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("provider summary contains duplicate example IDs")
    prediction_records = [record for record in records if record.trace.prediction is not None]
    predictions: list[HallucinationPrediction] = []
    for record in prediction_records:
        if record.trace.prediction is not None:
            predictions.append(record.trace.prediction)
    evaluated_ground_truth = {
        record.example_id: ground_truth[record.example_id] for record in prediction_records
    }
    evaluated_metadata = {
        record.example_id: metadata.get(record.example_id, {}) for record in prediction_records
    }
    classification = _classification_report(
        evaluated_ground_truth,
        predictions,
        evaluated_metadata,
    )
    task_slices = classification["slices"].get("task_type", {})
    human_slices: dict[str, dict[str, float]] = {}
    for label in (HallucinationLabel.GROUNDED.value, HallucinationLabel.HALLUCINATED.value):
        selected_ids = {
            example_id: label
            for example_id, value in evaluated_ground_truth.items()
            if value.value == label
        }
        sub_ground_truth = {
            example_id: evaluated_ground_truth[example_id] for example_id in selected_ids
        }
        sub_predictions = [
            prediction for prediction in predictions if prediction.example_id in selected_ids
        ]
        human_slices[label] = _classification_report(sub_ground_truth, sub_predictions)["metrics"]
    total = len(records)
    parse_failures = sum(
        record.trace.error_class in {"PARSE_ERROR", "SCHEMA_VALIDATION_ERROR"} for record in records
    )
    latencies = [
        record.trace.latency_ms for record in records if record.trace.latency_ms is not None
    ]
    return {
        "provider": next(iter(providers), "unknown"),
        "evaluated_count": len(prediction_records),
        "missing_count": total - len(prediction_records),
        "api_success_rate": (
            sum(record.trace.api_success for record in records) / total if total else 0.0
        ),
        "parse_success_rate": (
            sum(record.trace.parse_success for record in records) / total if total else 0.0
        ),
        "schema_validation_failure_rate": parse_failures / total if total else 0.0,
        "confusion_matrix": classification["confusion_matrix"],
        "metrics": classification["metrics"],
        "task_slices": task_slices,
        "human_label_slices": human_slices,
        "latency": _latency_summary(latencies),
        "token_usage": _token_summary(records),
        "false_positive_ids": [
            example_id
            for example_id, prediction in (
                (record.example_id, record.trace.prediction) for record in prediction_records
            )
            if prediction is not None
            and ground_truth[example_id] is HallucinationLabel.GROUNDED
            and prediction.label is HallucinationLabel.HALLUCINATED
        ],
        "false_negative_ids": [
            example_id
            for example_id, prediction in (
                (record.example_id, record.trace.prediction) for record in prediction_records
            )
            if prediction is not None
            and ground_truth[example_id] is HallucinationLabel.HALLUCINATED
            and prediction.label is HallucinationLabel.GROUNDED
        ],
    }


def compare_pilot_predictions(
    ground_truth: Mapping[str, HallucinationLabel],
    baseline: Mapping[str, HallucinationPrediction],
    candidate: Mapping[str, HallucinationPrediction],
) -> dict[str, Any]:
    """Compare two predictors on exactly the same IDs without majority voting."""

    expected = set(ground_truth)
    if set(baseline) != expected or set(candidate) != expected:
        raise ValueError("paired comparison requires identical example IDs")
    categories: dict[str, list[str]] = {
        "BOTH_CORRECT": [],
        "BASELINE_ONLY_CORRECT": [],
        "CANDIDATE_ONLY_CORRECT": [],
        "BOTH_WRONG": [],
    }
    baseline_correct: list[bool] = []
    candidate_correct: list[bool] = []
    baseline_fn_fixed: list[str] = []
    baseline_fp_fixed: list[str] = []
    candidate_fn: list[str] = []
    candidate_fp: list[str] = []
    for example_id in ground_truth:
        actual = ground_truth[example_id]
        baseline_is_correct = baseline[example_id].label is actual
        candidate_is_correct = candidate[example_id].label is actual
        baseline_correct.append(baseline_is_correct)
        candidate_correct.append(candidate_is_correct)
        if baseline_is_correct and candidate_is_correct:
            categories["BOTH_CORRECT"].append(example_id)
        elif baseline_is_correct:
            categories["BASELINE_ONLY_CORRECT"].append(example_id)
        elif candidate_is_correct:
            categories["CANDIDATE_ONLY_CORRECT"].append(example_id)
        else:
            categories["BOTH_WRONG"].append(example_id)
        if actual is HallucinationLabel.HALLUCINATED:
            if baseline[example_id].label is HallucinationLabel.GROUNDED:
                if candidate_is_correct:
                    baseline_fn_fixed.append(example_id)
            if candidate[example_id].label is HallucinationLabel.GROUNDED:
                candidate_fn.append(example_id)
        else:
            if baseline[example_id].label is HallucinationLabel.HALLUCINATED:
                if candidate_is_correct:
                    baseline_fp_fixed.append(example_id)
            if candidate[example_id].label is HallucinationLabel.HALLUCINATED:
                candidate_fp.append(example_id)
    return {
        "example_count": len(expected),
        "categories": categories,
        "baseline_fn_fixed_by_candidate": baseline_fn_fixed,
        "baseline_fp_fixed_by_candidate": baseline_fp_fixed,
        "candidate_false_negative_ids": candidate_fn,
        "candidate_false_positive_ids": candidate_fp,
        "mcnemar": exact_mcnemar(baseline_correct, candidate_correct).model_dump(mode="json"),
    }


def recommend_phase5b_judge(
    provider_summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Select a complete pilot provider using a deterministic quality-first rule."""

    candidates: list[dict[str, Any]] = []
    for provider in sorted(provider_summaries):
        summary = provider_summaries[provider]
        if not (
            summary.get("missing_count") == 0
            and summary.get("api_success_rate") == 1.0
            and summary.get("parse_success_rate") == 1.0
        ):
            continue
        metrics = summary.get("metrics", {})
        latency = summary.get("latency", {})
        token_usage = summary.get("token_usage", {})
        provenance = summary.get("provenance", {})
        candidates.append(
            {
                "provider": provider,
                "model": provenance.get("requested_model"),
                "balanced_accuracy": metrics.get("balanced_accuracy", 0.0),
                "f1": metrics.get("f1", 0.0),
                "false_positive_rate": metrics.get("false_positive_rate", 1.0),
                "parse_success_rate": summary.get("parse_success_rate", 0.0),
                "p95_ms": latency.get("p95_ms", float("inf")),
                "total_tokens": token_usage.get("total_tokens", float("inf")),
            }
        )

    candidates.sort(
        key=lambda candidate: (
            -float(candidate["balanced_accuracy"]),
            -float(candidate["f1"]),
            float(candidate["false_positive_rate"]),
            -float(candidate["parse_success_rate"]),
            float(candidate["p95_ms"]),
            float(candidate["total_tokens"]),
            str(candidate["provider"]),
        )
    )
    ranking = [
        {
            "provider": candidate["provider"],
            "model": candidate["model"],
            "balanced_accuracy": candidate["balanced_accuracy"],
            "f1": candidate["f1"],
            "false_positive_rate": candidate["false_positive_rate"],
            "parse_success_rate": candidate["parse_success_rate"],
            "p95_ms": candidate["p95_ms"],
            "total_tokens": candidate["total_tokens"],
        }
        for candidate in candidates
    ]
    if not candidates:
        return {
            "status": "UNVERIFIED",
            "provider": None,
            "model": None,
            "ranking": [],
            "rationale": (
                "No provider completed the pilot with API and parse success for every example."
            ),
        }
    winner = candidates[0]
    return {
        "status": "RECOMMENDED",
        "provider": winner["provider"],
        "model": winner["model"],
        "ranking": ranking,
        "rationale": (
            f"Selected {winner['provider']} by complete outputs, then balanced accuracy, F1, "
            "lower false-positive rate, parse reliability, lower p95 latency, and lower "
            "reported token use."
        ),
    }


def build_multi_evaluator_analysis(
    ground_truth: Mapping[str, HallucinationLabel],
    predictions: Mapping[str, Mapping[str, HallucinationPrediction]],
) -> dict[str, Any]:
    """Classify complete five-way patterns with human labels as the reference."""

    expected = set(ground_truth)
    missing = {
        name: sorted(expected - set(values))
        for name, values in predictions.items()
        if set(values) != expected
    }
    complete_ids = set.intersection(expected, *(set(values) for values in predictions.values()))
    categories: dict[str, list[str]] = {
        "ALL_EVALUATORS_CORRECT": [],
        "ALL_EVALUATORS_WRONG": [],
        "BOTH_LLM_CORRECT_HHEM_WRONG": [],
        "HHEM_CORRECT_BOTH_LLM_WRONG": [],
        "GEMINI_ONLY_CORRECT": [],
        "GROQ_ONLY_CORRECT": [],
        "HHEM_ONLY_CORRECT": [],
        "HEURISTIC_ONLY_CORRECT": [],
        "GEMINI_AND_HHEM_CORRECT": [],
        "GEMINI_AND_HEURISTIC_CORRECT": [],
        "HHEM_AND_HEURISTIC_CORRECT": [],
    }
    names = list(predictions)
    for example_id in sorted(complete_ids):
        actual = ground_truth[example_id]
        correctness = {
            name: values[example_id].label is actual for name, values in predictions.items()
        }
        correct_count = sum(correctness.values())
        if correct_count == len(names):
            categories["ALL_EVALUATORS_CORRECT"].append(example_id)
        elif correct_count == 0:
            categories["ALL_EVALUATORS_WRONG"].append(example_id)
        if correctness.get("gemini") and correctness.get("groq") and not correctness.get("hhem"):
            categories["BOTH_LLM_CORRECT_HHEM_WRONG"].append(example_id)
        if (
            correctness.get("hhem")
            and not correctness.get("gemini")
            and not correctness.get("groq")
        ):
            categories["HHEM_CORRECT_BOTH_LLM_WRONG"].append(example_id)
        if correct_count == 2:
            for pair_names, category in (
                (("gemini", "hhem"), "GEMINI_AND_HHEM_CORRECT"),
                (("gemini", "heuristic"), "GEMINI_AND_HEURISTIC_CORRECT"),
                (("hhem", "heuristic"), "HHEM_AND_HEURISTIC_CORRECT"),
            ):
                if all(correctness.get(name) for name in pair_names):
                    categories[category].append(example_id)
        if correct_count == 1:
            for name, category in (
                ("gemini", "GEMINI_ONLY_CORRECT"),
                ("groq", "GROQ_ONLY_CORRECT"),
                ("hhem", "HHEM_ONLY_CORRECT"),
                ("heuristic", "HEURISTIC_ONLY_CORRECT"),
            ):
                if correctness.get(name):
                    categories[category].append(example_id)
    return {
        "complete_example_count": len(complete_ids),
        "missing_by_evaluator": missing,
        "categories": categories,
    }


def summarize_consistency(records: Sequence[PilotRunRecord]) -> dict[str, Any]:
    """Measure repeated labels without replacing the primary run prediction."""

    groups: dict[str, list[PilotRunRecord]] = defaultdict(list)
    for record in records:
        groups[record.example_id].append(record)
    complete = {
        example_id: sorted(
            [record for record in values if record.trace.decision is not None],
            key=lambda record: record.attempt,
        )
        for example_id, values in groups.items()
    }
    complete = {example_id: values for example_id, values in complete.items() if len(values) == 3}
    pairwise_matches = 0
    pairwise_total = 0
    unanimous = 0
    disagreements: list[str] = []
    confidences: list[float] = []
    for example_id in sorted(complete):
        values = complete[example_id]
        labels = [record.trace.decision.label for record in values if record.trace.decision]
        confidences.extend(
            record.trace.decision.confidence for record in values if record.trace.decision
        )
        matches = sum(left is right for left, right in combinations(labels, 2))
        pairwise_matches += matches
        pairwise_total += 3
        if matches == 3:
            unanimous += 1
        else:
            disagreements.append(example_id)
    confidence_report = {
        "mean": fmean(confidences) if confidences else 0.0,
        "min": min(confidences) if confidences else 0.0,
        "max": max(confidences) if confidences else 0.0,
        "range": (max(confidences) - min(confidences)) if confidences else 0.0,
    }
    return {
        "example_count": len(complete),
        "three_run_label_agreement_rate": (
            pairwise_matches / pairwise_total if pairwise_total else 0.0
        ),
        "unanimous_agreement_rate": unanimous / len(complete) if complete else 0.0,
        "disagreement_examples": disagreements,
        "confidence": confidence_report,
        "incomplete_examples": sorted(set(groups) - set(complete)),
    }
