from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.evaluators.hallucination.hhem import (
    HHEM_MODEL_REPOSITORY,
    HHEM_MODEL_REVISION,
    HHEMHallucinationEvaluator,
    load_hhem_score_model,
    validate_hhem_manifest,
)
from evalops.models.hallucination import HallucinationLabel


class FakeHHEMScoreModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.offset = 0
        self.seen_pairs: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.seen_pairs.extend(pairs)
        scores = self.scores[self.offset : self.offset + len(pairs)]
        self.offset += len(pairs)
        return scores


def test_hhem_score_mapping_preserves_support_score_and_threshold_boundary() -> None:
    evaluator = HHEMHallucinationEvaluator(
        score_model=FakeHHEMScoreModel([0.0, 0.5, 1.0]),
        threshold=0.5,
        threshold_source="fixed-test-threshold",
    )

    predictions = evaluator.evaluate_batch(
        [
            ("context-a", "response-a"),
            ("context-b", "response-b"),
            ("context-c", "response-c"),
        ]
    )

    assert [prediction.label for prediction in predictions] == [
        HallucinationLabel.HALLUCINATED,
        HallucinationLabel.GROUNDED,
        HallucinationLabel.GROUNDED,
    ]
    assert [prediction.support_score for prediction in predictions] == [0.0, 0.5, 1.0]
    assert [prediction.example_id for prediction in predictions] == ["", "", ""]
    assert evaluator.config["threshold"] == 0.5
    assert evaluator.config["threshold_source"] == "fixed-test-threshold"


def test_hhem_batch_preserves_example_order_and_ids() -> None:
    evaluator = HHEMHallucinationEvaluator(score_model=FakeHHEMScoreModel([0.2, 0.8]))

    predictions = evaluator.evaluate_batch(
        [
            {"example_id": "first", "source_context": "c1", "response": "r1"},
            {"example_id": "second", "source_context": "c2", "response": "r2"},
        ]
    )

    assert [prediction.example_id for prediction in predictions] == ["first", "second"]


def test_hhem_rejects_invalid_scores() -> None:
    evaluator = HHEMHallucinationEvaluator(score_model=FakeHHEMScoreModel([1.1]))

    with pytest.raises(ValueError, match="support score must be between 0 and 1"):
        evaluator.evaluate("context", "response")


def test_hhem_provenance_constants_are_immutable_strings() -> None:
    assert HHEM_MODEL_REPOSITORY == "vectara/hallucination_evaluation_model"
    assert len(HHEM_MODEL_REVISION) == 40
    assert all(character in "0123456789abcdef" for character in HHEM_MODEL_REVISION)


def test_reviewed_hhem_manifest_matches_custom_code_hashes() -> None:
    manifest = json.loads(Path("models/manifests/hhem-2.1-open.json").read_text(encoding="utf-8"))

    validate_hhem_manifest(manifest, revision=HHEM_MODEL_REVISION)


def test_unreviewed_hhem_revision_is_rejected_before_model_execution() -> None:
    with pytest.raises(ValueError, match="not approved"):
        load_hhem_score_model(revision="main")
