"""Private comparison compatibility evidence, never raw user data in reasons."""

from __future__ import annotations

from datetime import AwareDatetime
from enum import StrEnum
from typing import Literal

from evalops.regression.comparison import RegressionReport

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

class ComparisonMode(StrEnum):
    CANONICAL = "CANONICAL"
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"


class ComparisonRecord(BaseModel):
    """Immutable local comparison; exploratory claims never become canonical."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-comparison-v1"] = "workspace-comparison-v1"
    comparison_id: str = Field(pattern=r"^comparison-[0-9a-f]{32}$")
    workspace_id: str = Field(pattern=r"^ws-[0-9a-f]{32}$")
    mode: ComparisonMode
    compatibility: ComparisonCompatibility
    baseline_run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    baseline_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    candidate_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: Literal["workspace-retrieval-regression-v1"]
    regression_report: RegressionReport
    created_at: AwareDatetime
