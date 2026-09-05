"""Framework-neutral, versioned public Evidence Contract V1 models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evalops.export.policy import (
    safe_identifier,
    safe_optional_text,
    safe_public_text,
    safe_string_map,
    stable_floats,
    stable_metrics,
)
from evalops.regression.comparison import MetricDirection, RegressionStatus

PUBLIC_EVIDENCE_SCHEMA_VERSION = "public-evidence-v1"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    NOT_RUN = "NOT_RUN"


class DataKind(StrEnum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    CURATED_DATASET = "CURATED_DATASET"
    OFFICIAL_BENCHMARK = "OFFICIAL_BENCHMARK"


class ClaimScope(StrEnum):
    INTEGRATION_ONLY = "INTEGRATION_ONLY"
    PROTOCOL_SPECIFIC = "PROTOCOL_SPECIFIC"
    BENCHMARK_RESULT = "BENCHMARK_RESULT"


class PublicArtifactBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["public-evidence-v1"] = "public-evidence-v1"
    artifact_id: str = Field(min_length=1)
    verification_status: VerificationStatus
    data_kind: DataKind
    claim_scope: ClaimScope
    limitations: list[str] = Field(default_factory=list)

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return safe_identifier(value, field="artifact_id")

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, values: list[str]) -> list[str]:
        return sorted({safe_public_text(value, field="limitation") for value in values})


class PublicRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_type: str
    run_id: str
    dataset_name: str
    dataset_version: str
    dataset_revision: str | None = None
    system_name: str
    model: str | None = None
    model_provider: str | None = None
    benchmark: str | None = None
    language: str | None = None
    split: str | None = None
    retriever: str | None = None
    retriever_version: str | None = None
    tokenization_strategy: str | None = None
    top_k: int = Field(ge=1)
    evaluator_versions: dict[str, str] = Field(default_factory=dict)
    random_seed: int | None = None
    timestamp: datetime
    git_commit: str | None = None

    @field_validator(
        "evaluation_type",
        "dataset_name",
        "dataset_version",
        "system_name",
        "dataset_revision",
        "model",
        "model_provider",
        "benchmark",
        "language",
        "split",
        "retriever",
        "retriever_version",
        "tokenization_strategy",
        mode="before",
    )
    @classmethod
    def validate_text(cls, value: str | None, info: object) -> str | None:
        field_name = getattr(info, "field_name", "metadata")
        return safe_optional_text(value, field=field_name)

    @field_validator("run_id", "git_commit")
    @classmethod
    def validate_identifiers(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return safe_identifier(value, field=getattr(info, "field_name", "identifier"))

    @field_validator("evaluator_versions")
    @classmethod
    def validate_evaluator_versions(cls, value: dict[str, str]) -> dict[str, str]:
        return safe_string_map(value, field="evaluator_versions")


class PublicEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ref: str
    metrics: dict[str, float] = Field(default_factory=dict)
    metrics_by_k: dict[str, dict[str, float]] = Field(default_factory=dict)
    failure_category: str = "PASS"
    retrieved_document_ids: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)

    @field_validator("record_ref")
    @classmethod
    def validate_record_ref(cls, value: str) -> str:
        return safe_identifier(value, field="record_ref")

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        return stable_metrics(value)

    @field_validator("metrics_by_k")
    @classmethod
    def validate_metrics_by_k(
        cls, value: dict[str, dict[str, float]]
    ) -> dict[str, dict[str, float]]:
        return {
            safe_identifier(str(key), field="metrics_by_k key"): stable_metrics(
                metrics, field=f"metrics_by_k.{key}"
            )
            for key, metrics in sorted(value.items(), key=lambda item: str(item[0]))
        }

    @field_validator("failure_category")
    @classmethod
    def validate_failure_category(cls, value: str) -> str:
        return safe_identifier(value, field="failure_category")

    @field_validator("retrieved_document_ids", "relevant_document_ids")
    @classmethod
    def validate_document_ids(cls, values: list[str]) -> list[str]:
        return [safe_identifier(value, field="document_id") for value in values]

    @field_validator("scores")
    @classmethod
    def validate_scores(cls, value: list[float]) -> list[float]:
        return stable_floats(value, field="scores")


class PublicFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ref: str
    category: str
    failure_class: str | None = None

    @field_validator("record_ref", "category", "failure_class")
    @classmethod
    def validate_identifiers(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return safe_identifier(value, field=getattr(info, "field_name", "identifier"))


class PublicRunArtifactV1(PublicArtifactBase):
    artifact_type: Literal["run"] = "run"
    run: PublicRunMetadata
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[PublicFailure] = Field(default_factory=list)
    evidence: list[PublicEvidenceRecord] = Field(default_factory=list)

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        return stable_metrics(value)


class PublicComparisonMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    direction: MetricDirection
    baseline_value: float | None = None
    candidate_value: float | None = None
    delta: float | None = None
    status: RegressionStatus
    reason: str

    @field_validator("metric_name")
    @classmethod
    def validate_metric_name(cls, value: str) -> str:
        return safe_identifier(value, field="metric_name")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return safe_public_text(value, field="comparison reason")

    @field_validator("baseline_value", "candidate_value", "delta")
    @classmethod
    def validate_values(cls, value: float | None, info: object) -> float | None:
        if value is None:
            return None
        return stable_floats([value], field=getattr(info, "field_name", "comparison value"))[0]


class PublicComparisonArtifactV1(PublicArtifactBase):
    artifact_type: Literal["comparison"] = "comparison"
    baseline_artifact_id: str
    candidate_artifact_id: str
    baseline_run_id: str | None = None
    candidate_run_id: str | None = None
    passed: bool
    comparisons: list[PublicComparisonMetric] = Field(default_factory=list)
    population_compatibility: str | None = None

    @field_validator(
        "baseline_artifact_id",
        "candidate_artifact_id",
        "baseline_run_id",
        "candidate_run_id",
    )
    @classmethod
    def validate_ids(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return safe_identifier(value, field=getattr(info, "field_name", "artifact_id"))

    @field_validator("population_compatibility")
    @classmethod
    def validate_population_compatibility(cls, value: str | None) -> str | None:
        return safe_optional_text(value, field="population_compatibility")


class PublicArtifactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_type: Literal["run", "comparison"]
    run_id: str | None = None
    dataset_name: str | None = None
    evaluation_type: str | None = None
    verification_status: VerificationStatus
    data_kind: DataKind
    claim_scope: ClaimScope
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("artifact_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return safe_identifier(value, field=getattr(info, "field_name", "artifact_id"))

    @field_validator("dataset_name", "evaluation_type")
    @classmethod
    def validate_text(cls, value: str | None, info: object) -> str | None:
        return safe_optional_text(value, field=getattr(info, "field_name", "metadata"))

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        return stable_metrics(value)


class PublicEvidenceIndexV1(PublicArtifactBase):
    artifact_type: Literal["index"] = "index"
    artifacts: list[PublicArtifactSummary] = Field(default_factory=list)


PublicArtifact = PublicRunArtifactV1 | PublicComparisonArtifactV1 | PublicEvidenceIndexV1
