"""Safe metadata and state contracts for the Phase 5A pilot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from evalops.models.hallucination import HallucinationLabel


class PilotExampleMetadata(BaseModel):
    """Tracked-safe metadata for one sampled RAGTruth example."""

    model_config = ConfigDict(extra="forbid")

    example_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    human_label: HallucinationLabel
    stratum: str = Field(min_length=1)


class PilotManifest(BaseModel):
    """Metadata-only deterministic pilot population."""

    model_config = ConfigDict(extra="forbid")

    pilot_id: str = Field(min_length=1)
    manifest_version: str = Field(min_length=1)
    dataset_revision: str = Field(min_length=1)
    split: str = Field(min_length=1)
    quality_filter: list[str] = Field(min_length=1)
    sampling_seed: int
    sampling_strategy: str = Field(min_length=1)
    records: list[PilotExampleMetadata] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> PilotManifest:
        ids = [record.example_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("pilot manifest example IDs must be unique")
        return self

    @property
    def example_ids(self) -> list[str]:
        return [record.example_id for record in self.records]

    @property
    def strata(self) -> list[str]:
        return sorted({record.stratum for record in self.records})

    @property
    def stratum_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.stratum] = counts.get(record.stratum, 0) + 1
        return dict(sorted(counts.items()))


class PilotRunRecord(BaseModel):
    """One provider/example outcome safe for ignored detailed state."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    example_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    status: str = Field(min_length=1)
    trace: JudgeEvaluationTrace
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def serialize_state_record(record: PilotRunRecord) -> dict[str, Any]:
    """Serialize only safe trace data; source and response are not present."""

    return record.model_dump(mode="json")
