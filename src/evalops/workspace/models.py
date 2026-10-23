"""Versioned persisted contracts for local Workspace metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

WORKSPACE_REGISTRY_SCHEMA_VERSION: Final[Literal["workspace-registry-v1"]] = "workspace-registry-v1"
WORKSPACE_SCHEMA_VERSION: Final[Literal["workspace-v1"]] = "workspace-v1"


class WorkspaceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workspace-v1"]
    workspace_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime


class WorkspaceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workspace-registry-v1"]
    workspace_ids: list[str]


WORKSPACE_STATE_SCHEMA_VERSION: Final[Literal["workspace-state-v1"]] = "workspace-state-v1"


class BaselinePointer(BaseModel):
    """Explicit snapshot of a completed local run, not an editable artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pinned_at: AwareDatetime


class WorkspaceState(BaseModel):
    """Versioned mutable pointer; historical run artifacts remain immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-state-v1"] = WORKSPACE_STATE_SCHEMA_VERSION
    baseline: BaselinePointer | None = None
