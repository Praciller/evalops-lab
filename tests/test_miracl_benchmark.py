from __future__ import annotations

from pathlib import Path

from evalops.benchmarks.miracl import run_miracl_benchmark, write_trec_run
from evalops.models.runs import RunConfig
from evalops.regression.comparison import MetricDirection, MetricRule, compare_metrics

FIXTURE = Path("datasets/fixtures/miracl-th-mini")


def _config(run_id: str) -> RunConfig:
    return RunConfig(
        run_id=run_id,
        dataset_name="miracl-th-mini",
        dataset_version="synthetic-fixture-v1",
        system_name="evalops-bm25-mini",
        top_k=5,
        retriever="bm25",
        evaluator_versions={"retrieval": "deterministic-v1"},
    )


def test_mini_fixture_runs_through_retriever_existing_metrics_and_artifact() -> None:
    result = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("mini-001"),
    )

    assert result.evaluation_type == "miracl_retrieval"
    assert result.metrics["recall_at_5"] >= 0.5
    assert result.details["benchmark"] == "miracl"
    assert result.details["query_count"] == 5
    assert result.details["corpus_count"] == 6
    assert result.details["failure_counts"]["RETRIEVAL_MISS"] >= 0
    assert result.details["per_query"]["1"]["retrieved_document_ids"]


def test_identical_mini_runs_have_identical_metrics_and_rankings() -> None:
    first = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("mini-001"),
    )
    second = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("mini-002"),
    )

    assert first.metrics == second.metrics
    assert first.details["per_query"] == second.details["per_query"]


def test_trec_run_export_is_standard_and_does_not_store_corpus_text(tmp_path: Path) -> None:
    result = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("mini-001"),
    )
    path = tmp_path / "run.trec"

    write_trec_run(result, path, tag="evalops-bm25")

    first_line = path.read_text(encoding="utf-8").splitlines()[0].split()
    assert first_line[1] == "Q0"
    assert first_line[5] == "evalops-bm25"
    assert "กรุงเทพมหานครเป็นเมืองหลวง" not in result.model_dump_json()


def test_mini_benchmark_results_can_be_compared_with_explicit_policy() -> None:
    baseline = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("baseline"),
    )
    candidate = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("candidate"),
    )
    report = compare_metrics(
        candidate.metrics,
        baseline.metrics,
        [
            MetricRule(
                metric_name="recall_at_5",
                direction=MetricDirection.HIGHER_IS_BETTER,
                max_degradation=0.05,
            )
        ],
    )

    assert report.passed


def test_nonstandard_top_k_is_also_reported() -> None:
    result = run_miracl_benchmark(
        topics_path=FIXTURE / "topics.tsv",
        qrels_path=FIXTURE / "qrels.tsv",
        corpus_paths=[FIXTURE / "corpus.jsonl"],
        config=_config("mini-top2").model_copy(update={"top_k": 2}),
    )

    assert "recall_at_2" in result.metrics
    assert 2 in result.details["metric_ks"]
