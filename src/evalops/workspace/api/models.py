"""Pydantic request and response models for the versioned Workspace API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evalops.workspace.application.runs import RunSnapshot
from evalops.workspace.comparison.models import (
    ComparisonCompatibility,
    ComparisonMode,
    ComparisonRecord,
    QueryFailureTransition,
)
from evalops.workspace.export.models import ExportClassification, ExportManifest
from evalops.workspace.ingestion.models import InputKind, InputManifest
from evalops.workspace.jobs.models import JobRecord, JobState, SafeJobError
from evalops.workspace.models import BaselinePointer, WorkspaceRecord


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


class InputSummary(StrictModel):
    input_id: str
    kind: str
    source_mode: str
    content_sha256: str
    record_count: int
    created_at: datetime

    @classmethod
    def from_manifest(cls, manifest: InputManifest) -> InputSummary:
        return cls(
            input_id=manifest.input_id,
            kind=manifest.kind,
            source_mode=manifest.source_mode,
            content_sha256=manifest.content_sha256,
            record_count=manifest.record_count,
            created_at=manifest.created_at,
        )


class InputListResponse(StrictModel):
    inputs: list[InputSummary]


class ReferenceInputRequest(StrictModel):
    kind: InputKind
    path: str = Field(min_length=1, max_length=4096)


class PairRequest(StrictModel):
    ground_truth_input_id: str
    predictions_input_id: str


class PairResponse(StrictModel):
    ground_truth_records: int
    prediction_records: int
    matching_query_count: int
    missing_prediction_count: int
    extra_prediction_count: int
    blocking_codes: list[str]
    warning_codes: list[str]


class RunSummary(StrictModel):
    run_id: str
    workspace_id: str
    run_name: str
    job_id: str | None = None
    ground_truth_input_id: str
    predictions_input_id: str
    ground_truth_sha256: str
    predictions_sha256: str
    evaluator_versions: dict[str, str]
    top_k: int
    system_name: str
    dataset_name: str
    dataset_version: str
    created_at: datetime
    metrics: dict[str, float] | None = None
    failure_counts: dict[str, int] | None = None
    result_sha256: str | None = None
    evalops_version: str | None = None

    @classmethod
    def from_snapshot(
        cls, snapshot: RunSnapshot, metrics: dict[str, float] | None = None
    ) -> RunSummary:
        return cls(
            run_id=snapshot.run_id,
            workspace_id=snapshot.workspace_id,
            run_name=snapshot.run_name,
            ground_truth_input_id=snapshot.ground_truth_input_id,
            predictions_input_id=snapshot.predictions_input_id,
            ground_truth_sha256=snapshot.ground_truth_content_sha256,
            predictions_sha256=snapshot.predictions_content_sha256,
            evaluator_versions=snapshot.config.evaluator_versions,
            top_k=snapshot.config.top_k,
            system_name=snapshot.config.system_name,
            dataset_name=snapshot.config.dataset_name,
            dataset_version=snapshot.config.dataset_version,
            created_at=snapshot.created_at,
            metrics=metrics,
        )


class RunListResponse(StrictModel):
    runs: list[RunSummary]


class JobSummary(StrictModel):
    schema_version: str
    job_id: str
    workspace_id: str
    run_id: str
    state: JobState
    revision: int
    cancel_requested: bool
    safe_error: SafeJobError | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: JobRecord) -> JobSummary:
        return cls.model_validate(record.model_dump(mode="python"))


class BaselineResponse(StrictModel):
    baseline: BaselinePointer | None


class SetBaselineRequest(StrictModel):
    run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    confirm_replace: bool = False


class CreateComparisonRequest(StrictModel):
    candidate_run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    mode: ComparisonMode = ComparisonMode.CANONICAL


class ComparisonListResponse(StrictModel):
    comparisons: list[ComparisonRecord]


class ComparisonConflictResponse(StrictModel):
    error: ErrorDetail
    compatibility: ComparisonCompatibility


class ComparisonFailuresResponse(StrictModel):
    comparison_id: str
    total_count: int
    transitions: list[QueryFailureTransition]


class ExportPreviewRequest(StrictModel):
    source_type: Literal["run", "comparison"]
    source_id: str = Field(pattern=r"^(?:run|comparison)-[0-9a-f]{32}$")
    classification: ExportClassification


class ExportListResponse(StrictModel):
    exports: list[ExportManifest]
