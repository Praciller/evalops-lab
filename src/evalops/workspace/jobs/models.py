"""Versioned, fail-closed persistent job state contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobState(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EVALUATING = "EVALUATING"
    ANALYZING = "ANALYZING"
    WRITING_ARTIFACT = "WRITING_ARTIFACT"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL_STATES = frozenset(
    {
        JobState.COMPLETE,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.INTERRUPTED,
    }
)

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.VALIDATING, JobState.CANCELLED, JobState.FAILED}),
    JobState.VALIDATING: frozenset(
        {
            JobState.EVALUATING,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.INTERRUPTED,
        }
    ),
    JobState.EVALUATING: frozenset(
        {
            JobState.ANALYZING,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.INTERRUPTED,
        }
    ),
    JobState.ANALYZING: frozenset(
        {
            JobState.WRITING_ARTIFACT,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.INTERRUPTED,
        }
    ),
    JobState.WRITING_ARTIFACT: frozenset(
        {
            JobState.COMPLETE,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.INTERRUPTED,
        }
    ),
    JobState.COMPLETE: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.INTERRUPTED: frozenset(),
}


class SafeJobError(BaseModel):
    """A safe code/message pair; raw input, exceptions and local paths are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    message: str = Field(min_length=1, max_length=200)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-job-v1"] = "workspace-job-v1"
    job_id: str = Field(pattern=r"^job-[0-9a-f]{32}$")
    workspace_id: str = Field(pattern=r"^ws-[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    state: JobState = JobState.QUEUED
    revision: int = Field(default=0, ge=0)
    cancel_requested: bool = False
    safe_error: SafeJobError | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_state(self) -> JobRecord:
        if self.safe_error is not None and self.state not in {
            JobState.FAILED,
            JobState.INTERRUPTED,
        }:
            raise ValueError("safe error is incompatible with job state")
        if self.state == JobState.FAILED and self.safe_error is None:
            raise ValueError("failed job must have a safe error")
        return self

    @classmethod
    def queued(cls, workspace_id: str, run_id: str) -> JobRecord:
        now = datetime.now(UTC)
        return cls(
            job_id=f"job-{uuid.uuid4().hex}",
            workspace_id=workspace_id,
            run_id=run_id,
            created_at=now,
            updated_at=now,
        )


class InvalidJobTransitionError(ValueError):
    """A persisted job cannot move to an unsupported state or stale revision."""
