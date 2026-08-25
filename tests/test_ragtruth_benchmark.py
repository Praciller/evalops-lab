from __future__ import annotations

from pathlib import Path

from evalops.benchmarks.ragtruth import run_ragtruth_benchmark
from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.hallucination.heuristic import HeuristicHallucinationEvaluator
from evalops.models.hallucination import AnnotationPolicy
from evalops.models.runs import RunConfig

FIXTURE = Path("datasets/fixtures/ragtruth-mini")


def _config() -> RunConfig:
    return RunConfig(
        run_id="ragtruth-mini-test",
        dataset_name="ragtruth-mini",
        dataset_version="synthetic-fixture-v1",
        system_name="heuristic-baseline",
        benchmark="ragtruth",
        split="test",
    )


def test_mini_benchmark_has_explicit_quality_filter_metrics_slices_and_fp_fn() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")
    result = run_ragtruth_benchmark(
        dataset,
        HeuristicHallucinationEvaluator(),
        config=_config(),
        annotation_policy=AnnotationPolicy.STRICT_GROUNDEDNESS,
        quality_filter={"good"},
    )

    assert result.evaluation_type == "ragtruth_hallucination"
    assert result.run.benchmark == "ragtruth"
    assert result.details["counts"] == {"total": 8, "included": 6, "excluded": 2}
    assert result.details["quality_filter"] == ["good"]
    assert result.details["annotation_policy"] == "strict-groundedness"
    assert result.details["confusion_matrix"] == {"tp": 4, "tn": 1, "fp": 0, "fn": 1}
    assert result.details["task_slices"]["QA"]["total"] == 3
    assert result.details["model_slices"]["mini-gpt"]["total"] >= 1
    assert result.details["false_negative_ids"] == ["r4-implicit-true"]
    assert result.details["per_example"]["r2-hallucinated"]["human_label"] == "HALLUCINATED"


def test_factual_correctness_policy_changes_only_implicit_true_ground_truth() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")
    strict = run_ragtruth_benchmark(
        dataset,
        HeuristicHallucinationEvaluator(),
        config=_config(),
        annotation_policy=AnnotationPolicy.STRICT_GROUNDEDNESS,
        quality_filter={"good"},
    )
    factual = run_ragtruth_benchmark(
        dataset,
        HeuristicHallucinationEvaluator(),
        config=_config().model_copy(update={"run_id": "ragtruth-mini-factual"}),
        annotation_policy=AnnotationPolicy.FACTUAL_CORRECTNESS,
        quality_filter={"good"},
    )

    assert strict.details["per_example"]["r4-implicit-true"]["human_label"] == "HALLUCINATED"
    assert factual.details["per_example"]["r4-implicit-true"]["human_label"] == "GROUNDED"
    assert factual.details["false_negative_ids"] == []
