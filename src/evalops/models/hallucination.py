"""Stable models for human-annotated hallucination evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HallucinationLabel(StrEnum):
    """Response-level binary labels, with hallucination as the positive class."""

    GROUNDED = "GROUNDED"
    HALLUCINATED = "HALLUCINATED"


class AnnotationPolicy(StrEnum):
    """Explicit interpretations of RAGTruth's word-level human annotations."""

    STRICT_GROUNDEDNESS = "strict-groundedness"
    FACTUAL_CORRECTNESS = "factual-correctness"


class HallucinationSpan(BaseModel):
    """One preserved human annotation and its offset validation state."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    label_type: str = "unknown"
    due_to_null: bool = False
    implicit_true: bool = False
    meta: Any = None
    offset_valid: bool | None = None
    validation_issues: list[str] = Field(default_factory=list)


class HallucinationExample(BaseModel):
    """Normalized RAGTruth response with human labels kept separate from predictions."""

    model_config = ConfigDict(extra="forbid")

    example_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    source_name: str = ""
    source_context: str = ""
    source_info: Any = None
    prompt: str = ""
    response: str
    spans: list[HallucinationSpan] = Field(default_factory=list)
    split: str = Field(min_length=1)
    quality: str = Field(min_length=1)
    model: str | None = None
    temperature: float | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
    raw_source: dict[str, Any] = Field(default_factory=dict)

    @property
    def span_validation_issues(self) -> list[str]:
        """Return all offset issues without altering the upstream annotation."""

        return [issue for span in self.spans for issue in span.validation_issues]

    def human_label(self, policy: AnnotationPolicy) -> HallucinationLabel:
        """Map word annotations to a response label under an explicit policy."""

        if policy is AnnotationPolicy.STRICT_GROUNDEDNESS:
            has_hallucination = bool(self.spans)
        else:
            has_hallucination = any(not span.implicit_true for span in self.spans)
        return HallucinationLabel.HALLUCINATED if has_hallucination else HallucinationLabel.GROUNDED


class DatasetAnnotationIssue(BaseModel):
    """A non-destructive adapter finding that must remain visible to callers."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    record_id: str | None = None


class HallucinationDataset(BaseModel):
    """Normalized dataset envelope used by all hallucination evaluators."""

    model_config = ConfigDict(extra="forbid")

    examples: list[HallucinationExample]
    source_revision: str = "unknown"
    response_sha256: str | None = None
    source_sha256: str | None = None
    validation_issues: list[DatasetAnnotationIssue] = Field(default_factory=list)

    @property
    def quality_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for example in self.examples:
            counts[example.quality] = counts.get(example.quality, 0) + 1
        return dict(sorted(counts.items()))


class PredictedHallucinationSpan(BaseModel):
    """Optional evaluator span output for future span-aware evaluators."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = ""


class HallucinationPrediction(BaseModel):
    """Evaluator output, deliberately separate from human ground truth."""

    model_config = ConfigDict(extra="forbid")

    example_id: str = ""
    label: HallucinationLabel
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    support_score: float | None = Field(default=None, ge=0.0, le=1.0)
    input_length: int | None = Field(default=None, ge=0)
    truncated: bool | None = None
    context_strategy: str | None = None
    predicted_spans: list[PredictedHallucinationSpan] = Field(default_factory=list)
    evaluator_name: str = ""
    evaluator_version: str = ""
    evaluator_config: dict[str, Any] = Field(default_factory=dict)
