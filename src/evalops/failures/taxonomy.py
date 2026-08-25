"""Failure labels are data, not arbitrary strings attached to a score."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FailureCategory(StrEnum):
    """Initial RAG failure vocabulary."""

    PASS = "PASS"
    RETRIEVAL_MISS = "RETRIEVAL_MISS"
    WRONG_ANSWER = "WRONG_ANSWER"
    HALLUCINATION = "HALLUCINATION"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    WRONG_CITATION = "WRONG_CITATION"
    INCOMPLETE_ANSWER = "INCOMPLETE_ANSWER"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"
    SHOULD_ABSTAIN = "SHOULD_ABSTAIN"
    DATASET_AMBIGUOUS = "DATASET_AMBIGUOUS"
    GROUND_TRUTH_ERROR = "GROUND_TRUTH_ERROR"
    HALLUCINATION_FALSE_POSITIVE = "HALLUCINATION_FALSE_POSITIVE"
    HALLUCINATION_FALSE_NEGATIVE = "HALLUCINATION_FALSE_NEGATIVE"
    PARTIAL_SPAN_MATCH = "PARTIAL_SPAN_MATCH"
    EVALUATOR_UNCERTAIN = "EVALUATOR_UNCERTAIN"


class FailureClass(StrEnum):
    """Ownership boundary for a failure or uncertainty."""

    SYSTEM = "system_failure"
    EVALUATOR_UNCERTAINTY = "evaluator_uncertainty"
    DATASET = "dataset_problem"


class FailureClassification(BaseModel):
    """A failure label with enough context for later analysis."""

    category: FailureCategory
    failure_class: FailureClass | None = None
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
