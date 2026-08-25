"""RAGTruth benchmark runner and traceable result artifact."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from evalops.evaluators.hallucination.interface import HallucinationEvaluator
from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.failures.taxonomy import FailureCategory, FailureClass, FailureClassification
from evalops.models.hallucination import AnnotationPolicy, HallucinationDataset
from evalops.models.runs import EvaluationResult, RunConfig


def _slice_payload(
    slices: Mapping[str, Mapping[str, Mapping[str, float]]],
    examples_by_dimension: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, dict[str, float]]]:
    payload: dict[str, dict[str, dict[str, float]]] = {}
    for dimension, values in slices.items():
        payload[dimension] = {}
        for value, metrics in values.items():
            payload[dimension][value] = {
                "total": float(examples_by_dimension[dimension][value]),
                **metrics,
            }
    return payload


def run_ragtruth_benchmark(
    dataset: HallucinationDataset,
    evaluator: HallucinationEvaluator,
    *,
    config: RunConfig,
    annotation_policy: AnnotationPolicy = AnnotationPolicy.STRICT_GROUNDEDNESS,
    quality_filter: Iterable[str] | None = None,
) -> EvaluationResult:
    """Run one evaluator without mixing human labels and predictions."""

    included_quality = set(quality_filter or {"good"})
    included = [example for example in dataset.examples if example.quality in included_quality]
    excluded = [example for example in dataset.examples if example.quality not in included_quality]
    ground_truth = {
        example.example_id: example.human_label(annotation_policy) for example in included
    }
    batch_evaluate = getattr(evaluator, "evaluate_batch", None)
    if callable(batch_evaluate):
        predictions = list(batch_evaluate(included))
    else:
        predictions = [
            evaluator.evaluate(
                example.source_context,
                example.response,
                example_id=example.example_id,
            )
            for example in included
        ]
    metadata = {
        example.example_id: {
            "task_type": example.task_type,
            "model": example.model or "unknown",
        }
        for example in included
    }
    report = evaluate_hallucination_predictions(ground_truth, predictions, metadata=metadata)
    failures: list[FailureClassification] = []
    prediction_map = {prediction.example_id: prediction for prediction in predictions}
    for example_id in report.false_positive_ids:
        failures.append(
            FailureClassification(
                category=FailureCategory.HALLUCINATION_FALSE_POSITIVE,
                failure_class=FailureClass.EVALUATOR_UNCERTAINTY,
                message="Evaluator predicted hallucination for a grounded human label.",
                evidence={"example_id": example_id},
            )
        )
    for example_id in report.false_negative_ids:
        failures.append(
            FailureClassification(
                category=FailureCategory.HALLUCINATION_FALSE_NEGATIVE,
                failure_class=FailureClass.EVALUATOR_UNCERTAINTY,
                message="Evaluator missed a hallucinated human label.",
                evidence={"example_id": example_id},
            )
        )
    for issue in dataset.validation_issues:
        failures.append(
            FailureClassification(
                category=FailureCategory.DATASET_AMBIGUOUS,
                failure_class=FailureClass.DATASET,
                message=issue.message,
                evidence={"code": issue.code, "record_id": issue.record_id},
            )
        )
    dimension_counts: dict[str, dict[str, int]] = {"task_type": {}, "model": {}}
    for example in included:
        for dimension, value in {
            "task_type": example.task_type,
            "model": example.model or "unknown",
        }.items():
            dimension_counts[dimension][value] = dimension_counts[dimension].get(value, 0) + 1
    per_example = {
        example.example_id: {
            "source_id": example.source_id,
            "task_type": example.task_type,
            "model": example.model,
            "quality": example.quality,
            "human_label": ground_truth[example.example_id].value,
            "predicted_label": prediction_map[example.example_id].label.value,
            "score": prediction_map[example.example_id].score,
            "support_score": prediction_map[example.example_id].support_score,
            "input_length": prediction_map[example.example_id].input_length,
            "truncated": prediction_map[example.example_id].truncated,
            "context_strategy": prediction_map[example.example_id].context_strategy,
            "human_span_count": len(example.spans),
            "span_validation_issue_count": len(example.span_validation_issues),
        }
        for example in included
    }
    updated_config = config.model_copy(
        update={
            "benchmark": "ragtruth",
            "annotation_policy": annotation_policy.value,
            "quality_filter": sorted(included_quality),
            "evaluator_versions": {
                **config.evaluator_versions,
                "hallucination": evaluator.version,
            },
            "evaluator_config": dict(evaluator.config),
        }
    )
    details: dict[str, Any] = {
        "benchmark": "ragtruth",
        "dataset_revision": dataset.source_revision,
        "counts": {
            "total": len(dataset.examples),
            "included": len(included),
            "excluded": len(excluded),
        },
        "excluded_ids": [example.example_id for example in excluded],
        "exclusion_reasons": {
            f"quality:{quality}": sum(example.quality == quality for example in excluded)
            for quality in sorted({example.quality for example in excluded})
        },
        "quality_filter": sorted(included_quality),
        "annotation_policy": annotation_policy.value,
        "evaluator": {
            "name": evaluator.name,
            "version": evaluator.version,
            "config": dict(evaluator.config),
        },
        "confusion_matrix": report.confusion_matrix.model_dump(mode="json"),
        "false_positive_ids": report.false_positive_ids,
        "false_negative_ids": report.false_negative_ids,
        "task_slices": _slice_payload(report.slices, dimension_counts)["task_type"],
        "model_slices": _slice_payload(report.slices, dimension_counts)["model"],
        "span_foundation": {
            "exact_match": "character offsets must match exactly",
            "character_overlap": "intersection length in characters",
            "character_iou": "intersection over union in characters",
            "status": "prediction spans not emitted by evaluator; response metrics only",
        },
        "validation_issue_count": len(dataset.validation_issues),
        "per_example": per_example,
    }
    return EvaluationResult(
        evaluation_type="ragtruth_hallucination",
        run=updated_config,
        metrics=report.metrics,
        failures=failures,
        details=details,
    )
