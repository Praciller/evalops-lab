from __future__ import annotations

import pytest

from evalops.evaluators.hallucination.thresholds import (
    analyze_thresholds,
    select_threshold_from_validation,
)
from evalops.models.hallucination import HallucinationLabel

SCORES = {"hall": 0.2, "ground": 0.8}
LABELS = {"hall": HallucinationLabel.HALLUCINATED, "ground": HallucinationLabel.GROUNDED}


def test_threshold_analysis_is_deterministic_and_uses_support_score_semantics() -> None:
    table = analyze_thresholds(SCORES, LABELS, [0.5, 0.2, 0.9])

    assert [row["threshold"] for row in table] == [0.2, 0.5, 0.9]
    assert table[1]["f1"] == 1.0
    assert table[2]["false_positive_rate"] == 1.0


def test_validation_threshold_selection_rejects_test_labels() -> None:
    with pytest.raises(ValueError, match="official test split"):
        select_threshold_from_validation(SCORES, LABELS, validation_split="test", candidates=[0.5])


def test_validation_threshold_selection_persists_method_and_seed() -> None:
    selection = select_threshold_from_validation(
        SCORES,
        LABELS,
        validation_split="source-group-validation",
        candidates=[0.3, 0.5, 0.7],
        random_seed=17,
    )

    assert selection.threshold == 0.3
    assert selection.threshold_source == "validation-derived"
    assert selection.random_seed == 17
