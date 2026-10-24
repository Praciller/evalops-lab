"""Strict, local-only request and preview models for opt-in public evidence."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from evalops.export.models import VerificationStatus


class WorkspaceExportDataKind(StrEnum):
    """Ad-hoc Workspace cannot assert official benchmark provenance."""

    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    CURATED_DATASET = "CURATED_DATASET"


class ExportClassification(BaseModel):
    """Owner-entered classification; completion cannot imply VERIFIED."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_status: VerificationStatus
    data_kind: WorkspaceExportDataKind
    limitations: list[str] = Field(default_factory=list)


class PreviewFile(BaseModel):
    """A disclosure of one exact, canonical, in-memory serialized output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class ExportPreview(BaseModel):
    """Pre-confirmation preview: no path, content, or publish affordance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-export-preview-v1"] = "workspace-export-preview-v1"
    preview_id: str = Field(pattern=r"^preview-[0-9a-f]{32}$")
    source_type: Literal["run", "comparison"]
    source_id: str
    eligible: bool
    blocking_reasons: list[str]
    output_files: list[PreviewFile]
    included: list[str]
    removed: list[str]
    transformed: list[str]
    classification: ExportClassification
    expires_at: AwareDatetime
