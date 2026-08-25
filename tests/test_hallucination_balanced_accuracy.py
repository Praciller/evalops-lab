from __future__ import annotations

from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


def test_balanced_accuracy_is_the_mean_of_recall_and_specificity() -> None:
    report = evaluate_hallucination_predictions(
        {
            "tp": HallucinationLabel.HALLUCINATED,
            "tn": HallucinationLabel.GROUNDED,
            "fp": HallucinationLabel.GROUNDED,
            "fn": HallucinationLabel.HALLUCINATED,
        },
        [
            HallucinationPrediction(example_id="tp", label=HallucinationLabel.HALLUCINATED),
            HallucinationPrediction(example_id="tn", label=HallucinationLabel.GROUNDED),
            HallucinationPrediction(example_id="fp", label=HallucinationLabel.HALLUCINATED),
            HallucinationPrediction(example_id="fn", label=HallucinationLabel.GROUNDED),
        ],
    )

    assert report.metrics["balanced_accuracy"] == 0.5
