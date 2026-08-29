from __future__ import annotations

from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction
from evalops.pilot.full_analysis import (
    bootstrap_confidence_intervals,
    summarize_full_predictions,
)


def _prediction(
    example_id: str, label: HallucinationLabel, score: float
) -> HallucinationPrediction:
    return HallucinationPrediction(example_id=example_id, label=label, score=score)


def _inputs() -> tuple[
    dict[str, HallucinationLabel],
    dict[str, HallucinationPrediction],
    dict[str, HallucinationPrediction],
    dict[str, dict[str, str]],
    dict[str, dict[str, int]],
]:
    ground_truth = {
        "a": HallucinationLabel.HALLUCINATED,
        "b": HallucinationLabel.GROUNDED,
        "c": HallucinationLabel.HALLUCINATED,
        "d": HallucinationLabel.GROUNDED,
    }
    local = {
        "a": _prediction("a", HallucinationLabel.HALLUCINATED, 0.9),
        "b": _prediction("b", HallucinationLabel.GROUNDED, 0.1),
        "c": _prediction("c", HallucinationLabel.GROUNDED, 0.4),
        "d": _prediction("d", HallucinationLabel.HALLUCINATED, 0.8),
    }
    hhem = {
        "a": _prediction("a", HallucinationLabel.HALLUCINATED, 0.8),
        "b": _prediction("b", HallucinationLabel.HALLUCINATED, 0.6),
        "c": _prediction("c", HallucinationLabel.HALLUCINATED, 0.7),
        "d": _prediction("d", HallucinationLabel.GROUNDED, 0.2),
    }
    metadata = {
        "a": {"task_type": "QA", "model": "m1"},
        "b": {"task_type": "QA", "model": "m1"},
        "c": {"task_type": "Summary", "model": "m2"},
        "d": {"task_type": "Summary", "model": "m2"},
    }
    lengths = {
        example_id: {"response_chars": index * 10, "source_context_chars": (4 - index) * 20}
        for index, example_id in enumerate(ground_truth, start=1)
    }
    return ground_truth, local, hhem, metadata, lengths


def test_full_summary_reports_slices_calibration_and_errors() -> None:
    ground_truth, local, _, metadata, lengths = _inputs()

    report = summarize_full_predictions(
        ground_truth,
        local,
        metadata,
        lengths,
        confidence={example_id: 0.8 for example_id in ground_truth},
    )

    assert report["example_count"] == 4
    assert report["confusion_matrix"] == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
    assert set(report["task_slices"]) == {"QA", "Summary"}
    assert set(report["source_model_slices"]) == {"m1", "m2"}
    assert set(report["length_slices"]["response_chars"]["slices"]) == {
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    }
    assert report["error_analysis"]["false_positive_ids"] == ["d"]
    assert report["error_analysis"]["false_negative_ids"] == ["c"]
    assert "decision_confidence" in report["calibration"]


def test_bootstrap_is_deterministic_and_reports_paired_intervals() -> None:
    ground_truth, local, hhem, _, _ = _inputs()
    ids = list(ground_truth)

    first = bootstrap_confidence_intervals(ids, ground_truth, local, hhem, seed=123, replicates=100)
    second = bootstrap_confidence_intervals(
        ids, ground_truth, local, hhem, seed=123, replicates=100
    )

    assert first == second
    assert first["seed"] == 123
    assert first["replicates"] == 100
    assert set(first["local_metric_intervals"]) == {
        "f1",
        "balanced_accuracy",
        "recall",
        "false_positive_rate",
    }
    assert set(first["local_minus_hhem_delta_intervals"]) == set(first["local_metric_intervals"])
