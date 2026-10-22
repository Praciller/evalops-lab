"""Private, versioned contracts for canonical Workspace retrieval inputs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InputKind(StrEnum):
    RETRIEVAL_GROUND_TRUTH = "retrieval_ground_truth"
    RETRIEVAL_PREDICTIONS = "retrieval_predictions"


class InputSourceMode(StrEnum):
    IMPORTED = "imported"
    REFERENCED = "referenced"


class InputManifest(BaseModel):
    """Durable private metadata; source_path must never be served publicly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-input-v1"] = "workspace-input-v1"
    input_id: str = Field(pattern=r"^input-[0-9a-f]{32}$")
    kind: InputKind
    source_mode: InputSourceMode
    canonical_format: Literal["retrieval-jsonl-v1"] = "retrieval-jsonl-v1"
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(gt=0)
    validation_status: Literal["VALID"] = "VALID"
    source_path: str | None = None
    stored_relative_path: str | None = None
    source_filename: str | None = None
    created_at: datetime


class InputValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_count: int = Field(gt=0)
    unique_query_count: int = Field(gt=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal["VALID"] = "VALID"


class InputRegistrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: InputManifest
    summary: InputValidationSummary


class CsvMapping(BaseModel):
    """Explicit two-column mapping; no expressions or automatic inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id_column: str = Field(min_length=1)
    document_ids_column: str = Field(min_length=1)
    document_ids_delimiter: str = Field(default="|", min_length=1, max_length=1)


class InputValidationError(ValueError):
    """Safe validation issue without source content or user-local paths."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
