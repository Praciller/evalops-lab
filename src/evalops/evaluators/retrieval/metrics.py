"""Reference implementations of deterministic retrieval metrics.

The functions intentionally use no external evaluation library.  Duplicate
retrieved IDs count once as a relevant hit, while precision retains ``k`` as
its denominator, making duplicate results visible as a ranking-quality issue.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from evalops.failures.taxonomy import FailureCategory, FailureClass, FailureClassification

RelevanceInput = Sequence[str] | Mapping[str, int | float]


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")


def _unique_in_order(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _relevance_map(relevant: RelevanceInput) -> dict[str, float]:
    if isinstance(relevant, Mapping):
        return {document_id: float(value) for document_id, value in relevant.items() if value > 0}
    return {document_id: 1.0 for document_id in relevant}


def precision_at_k(
    relevant_document_ids: RelevanceInput,
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float:
    """Return binary relevance precision at ``k``.

    ``k`` remains the denominator when fewer than ``k`` results are returned.
    """

    _validate_k(k)
    relevant = set(_relevance_map(relevant_document_ids))
    retrieved = retrieved_document_ids[:k]
    relevant_hits = sum(document_id in relevant for document_id in set(retrieved))
    return relevant_hits / k


def recall_at_k(
    relevant_document_ids: RelevanceInput,
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float:
    """Return the fraction of relevant documents found in the first ``k``."""

    _validate_k(k)
    relevant = set(_relevance_map(relevant_document_ids))
    if not relevant:
        return 0.0
    retrieved = set(retrieved_document_ids[:k])
    return len(relevant & retrieved) / len(relevant)


def hit_rate_at_k(
    relevant_document_ids: RelevanceInput,
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float:
    """Return one when at least one relevant document is in the first ``k``."""

    _validate_k(k)
    relevant = set(_relevance_map(relevant_document_ids))
    return float(bool(relevant & set(retrieved_document_ids[:k])))


def mean_reciprocal_rank(
    relevant_document_ids: RelevanceInput,
    retrieved_document_ids: Sequence[str],
) -> float:
    """Return reciprocal rank of the first relevant result for one query."""

    relevant = set(_relevance_map(relevant_document_ids))
    for rank, document_id in enumerate(retrieved_document_ids, start=1):
        if document_id in relevant:
            return 1 / rank
    return 0.0


def ndcg_at_k(
    relevant_document_ids: RelevanceInput,
    retrieved_document_ids: Sequence[str],
    k: int,
) -> float:
    """Return nDCG at k with duplicate ranks removed.

    Sequence inputs represent binary relevance. Mapping inputs preserve graded
    positive labels and use standard exponential gain.
    """

    _validate_k(k)
    relevance = _relevance_map(relevant_document_ids)
    relevant = set(relevance)
    if not relevant:
        return 0.0
    unique_retrieved = _unique_in_order(retrieved_document_ids)
    dcg = sum(
        (2 ** relevance[document_id] - 1) / math.log2(rank + 2)
        for rank, document_id in enumerate(unique_retrieved[:k])
        if document_id in relevant
    )
    ideal_relevance = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(
        (2**relevance_value - 1) / math.log2(rank + 2)
        for rank, relevance_value in enumerate(ideal_relevance)
    )
    return dcg / idcg if idcg else 0.0


class PerQueryRetrievalResult(BaseModel):
    """Metrics and deterministic classification for one query."""

    metrics: dict[str, float]
    failure_category: FailureCategory
    classification: FailureClassification


class RetrievalEvaluationResult(BaseModel):
    """Macro retrieval evaluation result."""

    k: int
    metrics: dict[str, float]
    per_query: dict[str, PerQueryRetrievalResult] = Field(default_factory=dict)


def _classify_retrieval(
    relevant_document_ids: RelevanceInput, retrieved_document_ids: Sequence[str]
) -> FailureClassification:
    if not relevant_document_ids:
        return FailureClassification(
            category=FailureCategory.SHOULD_ABSTAIN,
            failure_class=FailureClass.SYSTEM,
            message="no relevant document is available; answer generation should abstain",
        )
    if hit_rate_at_k(
        relevant_document_ids, retrieved_document_ids, len(retrieved_document_ids) or 1
    ):
        return FailureClassification(category=FailureCategory.PASS, message="retrieval hit")
    return FailureClassification(
        category=FailureCategory.RETRIEVAL_MISS,
        failure_class=FailureClass.SYSTEM,
        message="no relevant document was retrieved",
        evidence={"relevant_document_ids": list(relevant_document_ids)},
    )


def evaluate_retrieval(
    ground_truth: Mapping[str, RelevanceInput],
    predictions: Mapping[str, Sequence[str]],
    *,
    k: int,
) -> RetrievalEvaluationResult:
    """Evaluate all ground-truth queries; missing predictions are empty results."""

    _validate_k(k)
    per_query: dict[str, PerQueryRetrievalResult] = {}
    for query_id, relevant in ground_truth.items():
        retrieved = predictions.get(query_id, [])
        query_metrics = {
            f"precision_at_{k}": precision_at_k(relevant, retrieved, k),
            f"recall_at_{k}": recall_at_k(relevant, retrieved, k),
            f"hit_rate_at_{k}": hit_rate_at_k(relevant, retrieved, k),
            "mrr": mean_reciprocal_rank(relevant, retrieved),
            f"ndcg_at_{k}": ndcg_at_k(relevant, retrieved, k),
        }
        classification = _classify_retrieval(relevant, retrieved)
        per_query[query_id] = PerQueryRetrievalResult(
            metrics=query_metrics,
            failure_category=classification.category,
            classification=classification,
        )

    query_count = len(per_query)
    if query_count == 0:
        macro_metrics = {
            f"precision_at_{k}": 0.0,
            f"recall_at_{k}": 0.0,
            f"hit_rate_at_{k}": 0.0,
            "mrr": 0.0,
            f"ndcg_at_{k}": 0.0,
        }
    else:
        metric_names = next(iter(per_query.values())).metrics
        macro_metrics = {
            name: sum(item.metrics[name] for item in per_query.values()) / query_count
            for name in metric_names
        }

    return RetrievalEvaluationResult(k=k, metrics=macro_metrics, per_query=per_query)
