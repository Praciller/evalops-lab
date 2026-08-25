"""Models for manually curated RAG evaluation cases."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCategory(StrEnum):
    """Supported categories for the initial Thai RAG benchmark."""

    DIRECT_FACTUAL = "direct_factual"
    MULTI_DOCUMENT = "multi_document"
    AMBIGUOUS_QUERY = "ambiguous_query"
    NO_ANSWER = "no_answer"
    CONFLICTING_CONTEXT = "conflicting_context"
    TEMPORAL = "temporal"
    NUMERIC_REASONING = "numeric_reasoning"
    CITATION_SENSITIVE = "citation_sensitive"
    ADVERSARIAL_NOISE = "adversarial_noise"


class Difficulty(StrEnum):
    """Coarse human-curation difficulty label."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RAGCase(BaseModel):
    """Human-authored ground truth for one RAG evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    ground_truth: str = Field(min_length=1)
    relevant_document_ids: list[str] = Field(default_factory=list)
    acceptable_answers: list[str] = Field(default_factory=list)
    category: DatasetCategory
    difficulty: Difficulty
    requires_abstention: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetValidationIssue(BaseModel):
    """One actionable dataset-quality finding."""

    code: str
    message: str
    record_id: str | None = None


class DatasetValidationReport(BaseModel):
    """Stable, serializable result of dataset validation."""

    valid: bool
    records_checked: int
    issues: list[DatasetValidationIssue] = Field(default_factory=list)
