"""MIRACL benchmark orchestration using normalized EvalOps components."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from evalops.datasets.miracl import (
    iter_miracl_corpus,
    load_miracl_qrels,
    load_miracl_topics,
    validate_miracl_records,
)
from evalops.evaluators.retrieval.metrics import evaluate_retrieval
from evalops.models.runs import EvaluationResult, RunConfig
from evalops.retrieval.bm25 import BM25Retriever


def _metric_ks(top_k: int) -> tuple[int, ...]:
    metric_ks = [k for k in (1, 5, 10) if k <= top_k]
    if top_k not in metric_ks:
        metric_ks.append(top_k)
    return tuple(metric_ks)


def run_miracl_benchmark(
    *,
    topics_path: str | Path,
    qrels_path: str | Path,
    corpus_paths: Sequence[str | Path],
    config: RunConfig,
) -> EvaluationResult:
    """Run BM25 on normalized MIRACL inputs and return a persisted-run envelope."""

    started = time.perf_counter()
    topics = load_miracl_topics(topics_path)
    qrels = load_miracl_qrels(qrels_path)
    documents = [
        document for corpus_path in corpus_paths for document in iter_miracl_corpus(corpus_path)
    ]
    validation = validate_miracl_records(
        topics,
        qrels,
        corpus_document_ids={document.document_id for document in documents},
    )
    if not validation.valid:
        issue_text = "; ".join(f"{issue.code}: {issue.message}" for issue in validation.issues)
        raise ValueError(f"MIRACL validation failed: {issue_text}")

    retriever = BM25Retriever(documents)
    predictions: dict[str, list[str]] = {}
    scores: dict[str, list[float]] = {}
    for topic in topics:
        ranked = retriever.retrieve(topic, config.top_k)
        predictions[topic.query_id] = [result.document_id for result in ranked]
        scores[topic.query_id] = [result.score for result in ranked]

    metric_ks = _metric_ks(config.top_k)
    evaluations = {k: evaluate_retrieval(qrels, predictions, k=k) for k in metric_ks}
    top_evaluation = (
        evaluations[config.top_k] if config.top_k in evaluations else evaluations[metric_ks[-1]]
    )
    failures = [
        query_result.classification
        for query_result in top_evaluation.per_query.values()
        if query_result.failure_category != "PASS"
    ]
    observed_failure_counts = Counter(
        query_result.failure_category.value for query_result in top_evaluation.per_query.values()
    )
    failure_counts = {
        category: observed_failure_counts.get(category, 0)
        for category in ("PASS", "RETRIEVAL_MISS", "SHOULD_ABSTAIN")
    }
    per_query: dict[str, dict[str, object]] = {}
    for topic in topics:
        query_id = topic.query_id
        per_query[query_id] = {
            "query_id": query_id,
            "retrieved_document_ids": predictions[query_id],
            "scores": scores[query_id],
            "relevant_document_ids": [
                document_id
                for document_id, relevance in qrels.get(query_id, {}).items()
                if relevance > 0
            ],
            "relevance": qrels.get(query_id, {}),
            "metrics_by_k": {str(k): evaluations[k].per_query[query_id].metrics for k in metric_ks},
            "failure_category": top_evaluation.per_query[query_id].failure_category.value,
        }

    details: dict[str, object] = {
        "benchmark": "miracl",
        "language": config.language or "th",
        "split": config.split or "dev",
        "retriever": retriever.name,
        "retriever_version": retriever.version,
        "retriever_config": {"k1": retriever.k1, "b": retriever.b},
        "tokenization_strategy": retriever.tokenization_strategy,
        "metric_ks": list(metric_ks),
        "metrics_by_k": {str(k): evaluations[k].metrics for k in metric_ks},
        "query_count": len(topics),
        "corpus_count": len(documents),
        "qrel_count": sum(len(query_qrels) for query_qrels in qrels.values()),
        "failure_counts": failure_counts,
        "queries_with_retrieval_hit": failure_counts.get("PASS", 0),
        "queries_with_retrieval_miss": failure_counts.get("RETRIEVAL_MISS", 0),
        "per_query": per_query,
        "elapsed_seconds": time.perf_counter() - started,
    }
    return EvaluationResult(
        evaluation_type="miracl_retrieval",
        run=config,
        metrics=top_evaluation.metrics,
        failures=failures,
        details=details,
    )


def write_trec_run(
    result: EvaluationResult,
    path: str | Path,
    *,
    tag: str = "evalops-bm25",
) -> None:
    """Write ranked predictions in standard TREC run format."""

    per_query = result.details.get("per_query", {})
    lines: list[str] = []
    if isinstance(per_query, dict):
        for query_id, query_result in per_query.items():
            if not isinstance(query_result, dict):
                continue
            document_ids = query_result.get("retrieved_document_ids", [])
            query_scores = query_result.get("scores", [])
            if not isinstance(document_ids, list) or not isinstance(query_scores, list):
                continue
            for rank, (document_id, score) in enumerate(
                zip(document_ids, query_scores, strict=True), start=1
            ):
                lines.append(f"{query_id} Q0 {document_id} {rank} {float(score):.12g} {tag}")
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
