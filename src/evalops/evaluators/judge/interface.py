"""Judge output is intentionally separate from human ground truth."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class JudgeOutput(BaseModel):
    """Traceable output emitted by an LLM-as-a-Judge adapter."""

    case_id: str
    score: float | None = None
    label: str | None = None
    reasoning: str = ""
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)


class JudgeEvaluator(Protocol):
    """Protocol for future judge integrations; no provider is required now."""

    name: str
    version: str

    def evaluate(self, case_id: str, answer: str, context: str) -> JudgeOutput: ...
