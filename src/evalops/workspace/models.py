"""Versioned persisted contracts for local Workspace metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

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
