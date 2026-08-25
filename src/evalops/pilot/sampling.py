"""Deterministic RAGTruth pilot and consistency sampling."""

from __future__ import annotations

import random
from collections.abc import Iterable

from evalops.models.hallucination import (
    AnnotationPolicy,
    HallucinationDataset,
    HallucinationLabel,
)
from evalops.pilot.models import PilotExampleMetadata, PilotManifest

DEFAULT_PILOT_ID = "ragtruth-llm-judge-pilot-v1"
DEFAULT_PILOT_SEED = 20260825
DEFAULT_CONSISTENCY_SEED = 20260826
TASK_TYPES = ("QA", "Summary", "Data2txt")
LABELS = (HallucinationLabel.GROUNDED, HallucinationLabel.HALLUCINATED)


def _stratum(task_type: str, label: HallucinationLabel) -> str:
    return f"{task_type}:{label.value}"


def build_pilot_manifest(
    dataset: HallucinationDataset,
    *,
    seed: int = DEFAULT_PILOT_SEED,
    target_per_stratum: int = 20,
    dataset_revision: str | None = None,
    pilot_id: str = DEFAULT_PILOT_ID,
    quality_filter: Iterable[str] = ("good",),
) -> PilotManifest:
    """Sample sorted IDs without replacement across six fixed strata."""

    if target_per_stratum < 1:
        raise ValueError("target_per_stratum must be positive")
    quality_values = sorted(set(quality_filter))
    if not quality_values:
        raise ValueError("quality_filter must not be empty")
    eligible = [
        example
        for example in dataset.examples
        if example.split == "test" and example.quality in quality_values
    ]
    groups: dict[str, list[PilotExampleMetadata]] = {
        _stratum(task_type, label): [] for task_type in TASK_TYPES for label in LABELS
    }
    for example in eligible:
        label = example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS)
        key = _stratum(example.task_type, label)
        if key in groups:
            groups[key].append(
                PilotExampleMetadata(
                    example_id=example.example_id,
                    source_id=example.source_id,
                    task_type=example.task_type,
                    human_label=label,
                    stratum=key,
                )
            )
    rng = random.Random(seed)
    selected: list[PilotExampleMetadata] = []
    for key in sorted(groups):
        candidates = sorted(groups[key], key=lambda record: record.example_id)
        selected.extend(rng.sample(candidates, min(target_per_stratum, len(candidates))))
    selected.sort(key=lambda record: (record.stratum, record.example_id))
    return PilotManifest(
        pilot_id=pilot_id,
        manifest_version="ragtruth-llm-judge-manifest-v1",
        dataset_revision=dataset_revision or dataset.source_revision,
        split="test",
        quality_filter=quality_values,
        sampling_seed=seed,
        sampling_strategy=(
            "sorted-example-id random.Random sample without replacement per "
            "task_type-human_label stratum"
        ),
        records=selected,
    )


def build_consistency_manifest(
    manifest: PilotManifest,
    *,
    seed: int = DEFAULT_CONSISTENCY_SEED,
    per_stratum: int = 2,
) -> PilotManifest:
    """Select a fixed number of existing pilot IDs from every available stratum."""

    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")
    groups: dict[str, list[PilotExampleMetadata]] = {key: [] for key in manifest.strata}
    for record in manifest.records:
        groups[record.stratum].append(record)
    rng = random.Random(seed)
    selected: list[PilotExampleMetadata] = []
    for key in sorted(groups):
        candidates = sorted(groups[key], key=lambda record: record.example_id)
        selected.extend(rng.sample(candidates, min(per_stratum, len(candidates))))
    selected.sort(key=lambda record: (record.stratum, record.example_id))
    return PilotManifest(
        pilot_id=f"{manifest.pilot_id}-consistency-v1",
        manifest_version="ragtruth-llm-judge-consistency-manifest-v1",
        dataset_revision=manifest.dataset_revision,
        split=manifest.split,
        quality_filter=list(manifest.quality_filter),
        sampling_seed=seed,
        sampling_strategy=(
            "sorted-example-id random.Random sample without replacement per existing pilot stratum"
        ),
        records=selected,
    )
