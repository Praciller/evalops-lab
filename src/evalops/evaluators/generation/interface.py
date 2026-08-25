"""Explicit adapter contract for future answer-level evaluators."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from evalops.failures.taxonomy import FailureCategory
from evalops.models.datasets import RAGCase


class ContextDocument(BaseModel):
    """A retrieved document supplied to a generation evaluator."""

    document_id: str = Field(min_length=1)
    text: str


class GenerationEvaluation(BaseModel):
    """Output contract; it does not claim to produce a judgment by itself."""

    case_id: str
    evaluator_name: str
    evaluator_version: str
    scores: dict[str, float] = Field(default_factory=dict)
    failure_categories: list[FailureCategory] = Field(default_factory=list)
    notes: str = ""


class GenerationEvaluator(Protocol):
    """Protocol implemented by correctness/faithfulness evaluators later."""

    name: str
    version: str

    def evaluate(
        self,
        case: RAGCase,
        answer: str,
        contexts: Sequence[ContextDocument],
    ) -> GenerationEvaluation: ...
