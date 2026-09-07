"""Pydantic request and response models for the versioned Workspace API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from evalops.workspace.models import WorkspaceRecord


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BootstrapRequest(StrictModel):
    nonce: str = Field(min_length=1)


class SessionInfo(StrictModel):
    authenticated: bool


class WorkspaceSummary(StrictModel):
    schema_version: str
    workspace_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: WorkspaceRecord) -> WorkspaceSummary:
        return cls.model_validate(record.model_dump())


class WorkspaceListResponse(StrictModel):
    workspaces: list[WorkspaceSummary]


class WorkspaceNameRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=200)


class HealthResponse(StrictModel):
    status: str


class ErrorDetail(StrictModel):
    code: str
    message: str
    field: str | None
    retryable: bool


class ErrorResponse(StrictModel):
    error: ErrorDetail
