from __future__ import annotations

import pytest

from evalops.evaluators.hallucination.comparison import compare_hallucination_artifacts


def _artifact(candidate_label: str) -> dict[str, object]:
    return {
        "run": {"run_id": "run"},
        "metrics": {"f1": 0.5},
        "details": {
            "evaluator": {"name": "test"},
            "per_example": {
                "a": {
                    "human_label": "HALLUCINATED",
                    "predicted_label": candidate_label,
                    "score": 0.5,
                }
            },
        },
    }


def test_artifact_comparison_uses_only_per_example_labels_and_reports_metric_delta() -> None:
    report = compare_hallucination_artifacts(_artifact("GROUNDED"), _artifact("HALLUCINATED"))

    assert report["metric_delta"] == {"f1": 0.0}
    assert report["paired_comparison"]["categories"]["HHEM_ONLY_CORRECT"] == ["a"]


def test_artifact_comparison_rejects_different_populations() -> None:
    candidate = _artifact("HALLUCINATED")
    candidate["details"] = {
        "evaluator": {"name": "candidate"},
        "per_example": {"b": {"human_label": "HALLUCINATED", "predicted_label": "HALLUCINATED"}},
    }

    with pytest.raises(ValueError, match="identical example IDs"):
        compare_hallucination_artifacts(_artifact("GROUNDED"), candidate)
