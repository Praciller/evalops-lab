from __future__ import annotations

import pytest

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction
from evalops.pilot.analysis import (
    build_multi_evaluator_analysis,
    compare_pilot_predictions,
    summarize_consistency,
    summarize_provider_records,
)
from evalops.pilot.models import PilotRunRecord


def _prediction(example_id: str, label: HallucinationLabel) -> HallucinationPrediction:
    return HallucinationPrediction(example_id=example_id, label=label)


def _record(
    example_id: str,
    label: HallucinationLabel | None,
    *,
    provider: str = "gemini",
    attempt: int = 1,
    confidence: float = 0.8,
    latency_ms: float = 10.0,
) -> PilotRunRecord:
    decision = None
    prediction = None
    if label is not None:
        decision = {
            "label": label.value,
            "confidence": confidence,
            "unsupported_claims": ["unsupported"]
            if label is HallucinationLabel.HALLUCINATED
            else [],
            "reason": "Evidence.",
        }
        prediction = _prediction(example_id, label)
    trace = JudgeEvaluationTrace(
        example_id=example_id,
        provider=provider,
        requested_model="model",
        prediction=prediction,
        decision=decision,
        api_success=label is not None,
        parse_success=label is not None,
        structured_output_status="PASS" if label is not None else "PARSE_FAILED",
        latency_ms=latency_ms,
    )
    return PilotRunRecord(
        provider=provider,
        example_id=example_id,
        attempt=attempt,
        status="SUCCESS" if label is not None else "FAILED",
        trace=trace,
    )


def test_provider_summary_reuses_classification_metrics_and_counts_failures() -> None:
    ground_truth = {
        "a": HallucinationLabel.HALLUCINATED,
        "b": HallucinationLabel.GROUNDED,
        "c": HallucinationLabel.HALLUCINATED,
    }
    records = [
        _record("a", HallucinationLabel.HALLUCINATED),
        _record("b", HallucinationLabel.HALLUCINATED),
        _record("c", None),
    ]

    report = summarize_provider_records(
        records,
        ground_truth,
        {"a": {"task_type": "QA"}, "b": {"task_type": "Summary"}, "c": {"task_type": "QA"}},
    )

    assert report["confusion_matrix"] == {"tp": 1, "tn": 0, "fp": 1, "fn": 0}
    assert report["metrics"]["precision"] == 0.5
    assert report["metrics"]["recall"] == 1.0
    assert report["api_success_rate"] == 2 / 3
    assert report["parse_success_rate"] == 2 / 3
    assert report["missing_count"] == 1
    assert set(report["task_slices"]) == {"QA", "Summary"}


def test_pairwise_comparison_reports_fixed_and_new_errors() -> None:
    ground_truth = {
        "a": HallucinationLabel.HALLUCINATED,
        "b": HallucinationLabel.GROUNDED,
    }
    baseline = {
        "a": _prediction("a", HallucinationLabel.GROUNDED),
        "b": _prediction("b", HallucinationLabel.GROUNDED),
    }
    candidate = {
        "a": _prediction("a", HallucinationLabel.HALLUCINATED),
        "b": _prediction("b", HallucinationLabel.HALLUCINATED),
    }

    report = compare_pilot_predictions(ground_truth, baseline, candidate)

    assert report["baseline_fn_fixed_by_candidate"] == ["a"]
    assert report["candidate_false_positive_ids"] == ["b"]
    assert report["mcnemar"]["heuristic_wrong_candidate_correct"] == 1


def test_pairwise_comparison_rejects_mismatched_ids() -> None:
    with pytest.raises(ValueError, match="identical example IDs"):
        compare_pilot_predictions(
            {"a": HallucinationLabel.GROUNDED},
            {"a": _prediction("a", HallucinationLabel.GROUNDED)},
            {},
        )


def test_multi_evaluator_analysis_uses_human_as_reference_without_voting() -> None:
    ground_truth = {
        "all": HallucinationLabel.GROUNDED,
        "gemini": HallucinationLabel.HALLUCINATED,
    }
    predictions = {
        "heuristic": {
            "all": _prediction("all", HallucinationLabel.GROUNDED),
            "gemini": _prediction("gemini", HallucinationLabel.GROUNDED),
        },
        "hhem": {
            "all": _prediction("all", HallucinationLabel.GROUNDED),
            "gemini": _prediction("gemini", HallucinationLabel.GROUNDED),
        },
        "gemini": {
            "all": _prediction("all", HallucinationLabel.GROUNDED),
            "gemini": _prediction("gemini", HallucinationLabel.HALLUCINATED),
        },
        "groq": {
            "all": _prediction("all", HallucinationLabel.HALLUCINATED),
            "gemini": _prediction("gemini", HallucinationLabel.GROUNDED),
        },
    }

    analysis = build_multi_evaluator_analysis(ground_truth, predictions)

    assert analysis["categories"]["ALL_EVALUATORS_CORRECT"] == []
    assert analysis["categories"]["GEMINI_ONLY_CORRECT"] == ["gemini"]
    assert analysis["complete_example_count"] == 2


def test_consistency_reports_pairwise_and_unanimous_agreement() -> None:
    records = [
        _record("a", HallucinationLabel.GROUNDED, attempt=1),
        _record("a", HallucinationLabel.GROUNDED, attempt=2),
        _record("a", HallucinationLabel.HALLUCINATED, attempt=3),
        _record("b", HallucinationLabel.HALLUCINATED, attempt=1),
        _record("b", HallucinationLabel.HALLUCINATED, attempt=2),
        _record("b", HallucinationLabel.HALLUCINATED, attempt=3),
    ]

    report = summarize_consistency(records)

    assert report["example_count"] == 2
    assert report["three_run_label_agreement_rate"] == 4 / 6
    assert report["unanimous_agreement_rate"] == 0.5
    assert report["disagreement_examples"] == ["a"]
    assert report["confidence"]["min"] == 0.8
