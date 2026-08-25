"""Traceability models for reproducible evaluation runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evalops.failures.taxonomy import FailureClassification


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunConfig(BaseModel):
    """Configuration and provenance recorded with every evaluation result."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    system_name: str = Field(min_length=1)
    model: str | None = None
    model_provider: str | None = None
    prompt_version: str | None = None
    retriever: str | None = None
    embedding_model: str | None = None
    top_k: int = Field(default=5, ge=1)
    evaluator_versions: dict[str, str] = Field(default_factory=dict)
    random_seed: int | None = None
    timestamp: datetime = Field(default_factory=_utc_now)
    git_commit: str | None = None
    benchmark: str | None = None
    language: str | None = None
    split: str | None = None
    dataset_revision: str | None = None
    corpus_revision: str | None = None
    tokenization_strategy: str | None = None
    retriever_version: str | None = None
    retriever_config: dict[str, Any] = Field(default_factory=dict)
    annotation_policy: str | None = None
    quality_filter: list[str] = Field(default_factory=list)
    evaluator_config: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Common structured result envelope for evaluator runs."""

    model_config = ConfigDict(extra="forbid")

    evaluation_type: str = Field(min_length=1)
    run: RunConfig
    metrics: dict[str, float]
    failures: list[FailureClassification] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
