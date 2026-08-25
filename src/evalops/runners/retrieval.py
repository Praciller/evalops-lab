"""Application-level retrieval evaluation orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from evalops.evaluators.retrieval.metrics import evaluate_retrieval
from evalops.models.runs import EvaluationResult, RunConfig


def run_retrieval_evaluation(
    ground_truth: Mapping[str, Sequence[str]],
    predictions: Mapping[str, Sequence[str]],
    config: RunConfig,
) -> EvaluationResult:
    """Run deterministic retrieval metrics and wrap them in a traceable result."""

    retrieval_result = evaluate_retrieval(ground_truth, predictions, k=config.top_k)
    failures = [
        query_result.classification
        for query_result in retrieval_result.per_query.values()
        if query_result.failure_category != "PASS"
    ]
    return EvaluationResult(
        evaluation_type="retrieval",
        run=config,
        metrics=retrieval_result.metrics,
        failures=failures,
        details={
            "k": retrieval_result.k,
            "per_query": retrieval_result.per_query,
            "prediction_query_count": len(predictions),
        },
    )
