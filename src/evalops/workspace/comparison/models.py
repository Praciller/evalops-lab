"""Private comparison compatibility evidence, never raw user data in reasons."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ComparisonCompatibilityStatus(StrEnum):
    COMPARABLE = "COMPARABLE"
    NON_COMPARABLE = "NON_COMPARABLE"


class CompatibilityReason(BaseModel):
    """Safe reason: field plus non-sensitive mismatch indicators only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    baseline: str
    candidate: str


class ComparisonCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ComparisonCompatibilityStatus
    reasons: list[CompatibilityReason]


class RetrievalPopulationEvidence(BaseModel):
    """Derived from checksum-verified private inputs, not browser-supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ground_truth_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_query_ids_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_query_ids_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_query_count: int = Field(gt=0)
    prediction_query_count: int = Field(ge=0)
