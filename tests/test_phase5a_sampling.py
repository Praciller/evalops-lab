from __future__ import annotations

import json

from evalops.models.hallucination import (
    HallucinationDataset,
    HallucinationExample,
    HallucinationLabel,
    HallucinationSpan,
)
from evalops.pilot.sampling import build_consistency_manifest, build_pilot_manifest


def _fixture_dataset() -> HallucinationDataset:
    examples: list[HallucinationExample] = []
    for task_type in ("QA", "Summary", "Data2txt"):
        for label in (HallucinationLabel.GROUNDED, HallucinationLabel.HALLUCINATED):
            for index in range(20):
                example_id = f"{task_type}-{label.value}-{index}"
                response = f"PRIVATE_RESPONSE_{example_id}"
                spans = (
                    [HallucinationSpan(start=0, end=7, text="PRIVATE")]
                    if label is HallucinationLabel.HALLUCINATED
                    else []
                )
                examples.append(
                    HallucinationExample(
                        example_id=example_id,
                        source_id=f"source-{example_id}",
                        task_type=task_type,
                        source_context=f"PRIVATE_CONTEXT_{example_id}",
                        response=response,
                        spans=spans,
                        split="test",
                        quality="good",
                    )
                )
    return HallucinationDataset(examples=examples, source_revision="fixture-revision")


def test_sampling_is_deterministic_and_has_six_strata() -> None:
    dataset = _fixture_dataset()
    manifest_a = build_pilot_manifest(dataset, target_per_stratum=1, seed=20260825)
    manifest_b = build_pilot_manifest(dataset, target_per_stratum=1, seed=20260825)

    assert manifest_a.model_dump(mode="json") == manifest_b.model_dump(mode="json")
    assert len(manifest_a.example_ids) == 6
    assert len(manifest_a.strata) == 6
    assert all(count == 1 for count in manifest_a.stratum_counts.values())


def test_manifest_serialization_contains_only_safe_metadata() -> None:
    manifest = build_pilot_manifest(_fixture_dataset(), target_per_stratum=1)
    serialized = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False)

    assert "source_context" not in serialized
    assert "response" not in serialized
    assert "The capital" not in serialized
    assert all(record.source_id for record in manifest.records)


def test_consistency_sampling_takes_two_examples_per_stratum() -> None:
    manifest = build_pilot_manifest(_fixture_dataset(), target_per_stratum=20)

    consistency = build_consistency_manifest(manifest, seed=20260826, per_stratum=2)

    assert len(consistency.example_ids) == 12
    assert consistency.sampling_seed == 20260826
    assert all(count == 2 for count in consistency.stratum_counts.values())


def test_full_pilot_target_is_120_with_20_per_stratum() -> None:
    manifest = build_pilot_manifest(_fixture_dataset(), target_per_stratum=20)

    assert len(manifest.example_ids) == 120
    assert len(manifest.strata) == 6
    assert all(count == 20 for count in manifest.stratum_counts.values())
