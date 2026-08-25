from __future__ import annotations

from evalops.evaluators.hallucination.metrics import (
    evaluate_hallucination_predictions,
)
from evalops.evaluators.hallucination.spans import (
    character_iou,
    character_overlap,
    exact_span_match,
)
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


def test_binary_metrics_treat_hallucinated_as_positive_and_include_zero_safe_rates() -> None:
    predictions = [
        HallucinationPrediction(example_id="tp", label=HallucinationLabel.HALLUCINATED, score=0.9),
        HallucinationPrediction(example_id="tn", label=HallucinationLabel.GROUNDED, score=0.1),
        HallucinationPrediction(example_id="fp", label=HallucinationLabel.HALLUCINATED, score=0.8),
        HallucinationPrediction(example_id="fn", label=HallucinationLabel.GROUNDED, score=0.2),
    ]

    report = evaluate_hallucination_predictions(
        {
            "tp": HallucinationLabel.HALLUCINATED,
            "tn": HallucinationLabel.GROUNDED,
            "fp": HallucinationLabel.GROUNDED,
            "fn": HallucinationLabel.HALLUCINATED,
        },
        predictions,
    )

    assert report.confusion_matrix.model_dump() == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
    assert report.metrics["precision"] == 0.5
    assert report.metrics["recall"] == 0.5
    assert report.metrics["f1"] == 0.5
    assert report.metrics["specificity"] == 0.5
    assert report.metrics["false_positive_rate"] == 0.5
    assert report.metrics["false_negative_rate"] == 0.5
    assert report.false_positive_ids == ["fp"]
    assert report.false_negative_ids == ["fn"]


def test_slice_metrics_are_reported_by_task_and_model() -> None:
    predictions = [
        HallucinationPrediction(example_id="a", label=HallucinationLabel.HALLUCINATED),
        HallucinationPrediction(example_id="b", label=HallucinationLabel.GROUNDED),
    ]
    report = evaluate_hallucination_predictions(
        {"a": HallucinationLabel.HALLUCINATED, "b": HallucinationLabel.HALLUCINATED},
        predictions,
        metadata={
            "a": {"task_type": "QA", "model": "m1"},
            "b": {"task_type": "Summary", "model": "m2"},
        },
    )

    assert report.slices["task_type"]["QA"]["recall"] == 1.0
    assert report.slices["task_type"]["Summary"]["false_negative_rate"] == 1.0
    assert report.slices["model"]["m1"]["precision"] == 1.0


def test_span_foundation_distinguishes_exact_overlap_and_iou() -> None:
    assert exact_span_match((2, 5), (2, 5)) is True
    assert exact_span_match((2, 5), (2, 6)) is False
    assert character_overlap((2, 6), (4, 8)) == 2
    assert character_iou((2, 6), (4, 8)) == 1 / 3
