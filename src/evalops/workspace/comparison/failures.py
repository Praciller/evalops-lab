"""Private per-query transitions: use persisted evaluator decisions without rescoring."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from evalops.evaluators.retrieval.metrics import PerQueryRetrievalResult
from evalops.failures.taxonomy import FailureCategory
from evalops.models.runs import EvaluationResult
from evalops.workspace.comparison.models import FailureTransition, QueryFailureTransition


def _per_query(result: EvaluationResult) -> dict[str, PerQueryRetrievalResult]:
    """Fail closed on absent or malformed evaluator-owned query details."""

    raw = result.details.get("per_query")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("local retrieval per-query evidence is missing")
    records: dict[str, PerQueryRetrievalResult] = {}
    for query_id, payload in raw.items():
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("local retrieval query identity is invalid")
        if not isinstance(payload, (Mapping, PerQueryRetrievalResult)):
            raise ValueError("local retrieval query evidence is invalid")
        try:
            records[query_id] = PerQueryRetrievalResult.model_validate(payload)
        except ValidationError as error:
            raise ValueError("local retrieval query evidence is invalid") from error
    return records


def build_failure_transitions(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> list[QueryFailureTransition]:
    """Use existing per-query labels; never recompute or guess metric semantics."""

    if baseline.evaluation_type != "retrieval" or candidate.evaluation_type != "retrieval":
        raise ValueError("failure transitions support retrieval results only")
    baseline_queries = _per_query(baseline)
    candidate_queries = _per_query(candidate)
    if baseline_queries.keys() != candidate_queries.keys():
        raise ValueError("local retrieval query populations do not match")

    transitions = []
    for query_id in sorted(baseline_queries):
        old = baseline_queries[query_id]
        new = candidate_queries[query_id]
        if old.failure_category == FailureCategory.PASS:
            outcome = (
                FailureTransition.UNCHANGED_PASS
                if new.failure_category == FailureCategory.PASS
                else FailureTransition.REGRESSED
            )
        elif new.failure_category == FailureCategory.PASS:
            outcome = FailureTransition.IMPROVED
        elif old.failure_category == new.failure_category:
            outcome = FailureTransition.PERSISTENT_FAILURE
        else:
            outcome = FailureTransition.CHANGED_FAILURE

        transitions.append(
            QueryFailureTransition(
                query_id=query_id,
                transition=outcome,
                baseline_category=old.failure_category,
                candidate_category=new.failure_category,
                baseline_metrics=old.metrics,
                candidate_metrics=new.metrics,
            )
        )
    return transitions
