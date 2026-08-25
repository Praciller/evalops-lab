"""Contracts for strict-groundedness judge outputs."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class JudgeLabel(StrEnum):
    """Binary labels emitted by the groundedness judge."""

    HALLUCINATED = "HALLUCINATED"
    GROUNDED = "GROUNDED"


ShortText = Annotated[str, Field(max_length=300)]


class JudgeDecision(BaseModel):
    """Validated public decision; hidden reasoning is intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    label: JudgeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[ShortText]
    reason: ShortText

    @model_validator(mode="after")
    def validate_label_evidence_consistency(self) -> JudgeDecision:
        if self.label is JudgeLabel.HALLUCINATED and not self.unsupported_claims:
            raise ValueError("unsupported_claims must be non-empty for HALLUCINATED")
        if self.label is JudgeLabel.GROUNDED and self.unsupported_claims:
            raise ValueError("unsupported_claims must be empty for GROUNDED")
        return self


class JudgeParseResult(BaseModel):
    """Safe parse outcome used by provider traces and pilot state."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    decision: JudgeDecision | None = None
    error_class: str | None = None
    safe_error_summary: str | None = None


def parse_judge_payload(payload: str | bytes | Any) -> JudgeParseResult:
    """Parse and validate one provider content value without semantic repair."""

    try:
        parsed = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    except (TypeError, ValueError, json.JSONDecodeError):
        return JudgeParseResult(
            success=False,
            error_class="PARSE_ERROR",
            safe_error_summary="Judge content was not valid JSON.",
        )
    if not isinstance(parsed, dict):
        return JudgeParseResult(
            success=False,
            error_class="PARSE_ERROR",
            safe_error_summary="Judge JSON root was not an object.",
        )
    try:
        decision = JudgeDecision.model_validate(parsed)
    except ValidationError:
        return JudgeParseResult(
            success=False,
            error_class="SCHEMA_VALIDATION_ERROR",
            safe_error_summary="Judge JSON failed the required schema or consistency rules.",
        )
    return JudgeParseResult(success=True, decision=decision)
