"""Private retrieval input compatibility and immutable run snapshot creation."""

from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from evalops.datasets.io import load_retrieval_ground_truth, load_retrieval_predictions
from evalops.models.runs import RunConfig
from evalops.workspace.ingestion.models import InputKind, InputManifest, InputValidationError
from evalops.workspace.storage import (
    UnknownInputError,
    WorkspaceStorageError,
    WorkspaceStore,
)

NonEmptyLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ValidationIssue(BaseModel):
    """Safe machine-readable code and message, with no raw private file paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class RetrievalPairValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ground_truth_records: int
    prediction_records: int
    matching_query_count: int
    missing_prediction_query_ids: list[str]
    extra_prediction_query_ids: list[str]
    blocking_issues: list[ValidationIssue]
    warnings: list[ValidationIssue]


class CreateRetrievalRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_name: NonEmptyLabel
    ground_truth_input_id: str
    predictions_input_id: str
    top_k: int = Field(ge=1)
    system_name: NonEmptyLabel
    dataset_name: NonEmptyLabel
    dataset_version: NonEmptyLabel


class RunSnapshot(BaseModel):
    """Private immutable on-disk run configuration; no public evidence status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["workspace-run-v1"] = "workspace-run-v1"
    run_id: str = Field(pattern=r"^run-[0-9a-f]{32}$")
    workspace_id: str
    run_name: str
    ground_truth_input_id: str
    ground_truth_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_input_id: str
    predictions_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: RunConfig
    created_at: datetime


class IncompatibleInputsError(ValueError):
    """Run creation requires two correctly typed inputs and intact checksums."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("retrieval inputs cannot be paired safely")


def _load_records(data: bytes, kind: InputKind) -> dict[str, list[str]]:
    """Feed captured bytes to the same loaders used by CLI and retrieval runs."""

    with tempfile.TemporaryDirectory(prefix="evalops-workspace-pair-") as directory:
        staged = Path(directory) / "validated.jsonl"
        staged.write_bytes(data)
        try:
            if kind == InputKind.RETRIEVAL_GROUND_TRUTH:
                return load_retrieval_ground_truth(staged)
            return load_retrieval_predictions(staged)
        except (OSError, ValueError) as error:
            raise InputValidationError("INVALID_INPUT", "registered input is invalid") from error


def _read_registered(
    store: WorkspaceStore, workspace_id: str, input_id: str, expected: InputKind
) -> tuple[InputManifest, dict[str, list[str]]]:
    manifest = store.get_input(workspace_id, input_id)
    if manifest.kind != expected:
        raise InputValidationError("WRONG_INPUT_KIND", "retrieval input kind is incorrect")
    content = store.read_input_bytes(workspace_id, input_id)
    return manifest, _load_records(content, expected)


def validate_retrieval_pair(
    store: WorkspaceStore,
    workspace_id: str,
    ground_truth_input_id: str,
    predictions_input_id: str,
) -> RetrievalPairValidation:
    """Validate an owned pair using its actual query population and stored hashes."""

    store.get_workspace(workspace_id)
    inputs: list[dict[str, list[str]]] = []
    blocking: list[ValidationIssue] = []
    for input_id, expected in (
        (ground_truth_input_id, InputKind.RETRIEVAL_GROUND_TRUTH),
        (predictions_input_id, InputKind.RETRIEVAL_PREDICTIONS),
    ):
        try:
            _, records = _read_registered(store, workspace_id, input_id, expected)
            inputs.append(records)
        except (UnknownInputError, WorkspaceStorageError, InputValidationError) as error:
            code = error.code if isinstance(error, InputValidationError) else "INVALID_INPUT"
            blocking.append(ValidationIssue(code=code, message="input is unavailable or invalid"))
            inputs.append({})
    if blocking:
        return RetrievalPairValidation(
            ground_truth_records=len(inputs[0]),
            prediction_records=len(inputs[1]),
            matching_query_count=0,
            missing_prediction_query_ids=[],
            extra_prediction_query_ids=[],
            blocking_issues=blocking,
            warnings=[],
        )
    truth_ids, prediction_ids = set(inputs[0]), set(inputs[1])
    missing = sorted(truth_ids - prediction_ids)
    extra = sorted(prediction_ids - truth_ids)
    warnings = []
    if missing:
        warnings.append(
            ValidationIssue(code="MISSING_PREDICTIONS", message="some queries have no predictions")
        )
    if extra:
        warnings.append(
            ValidationIssue(code="EXTRA_PREDICTIONS", message="some predictions lack ground truth")
        )
    return RetrievalPairValidation(
        ground_truth_records=len(truth_ids),
        prediction_records=len(prediction_ids),
        matching_query_count=len(truth_ids & prediction_ids),
        missing_prediction_query_ids=missing,
        extra_prediction_query_ids=extra,
        blocking_issues=[],
        warnings=warnings,
    )


def create_retrieval_run(
    store: WorkspaceStore,
    workspace_id: str,
    request: CreateRetrievalRun,
    *,
    git_commit: str | None = None,
) -> RunSnapshot:
    """Save one constrained run config; the job queue will be added in Task 4."""

    validation = validate_retrieval_pair(
        store, workspace_id, request.ground_truth_input_id, request.predictions_input_id
    )
    if validation.blocking_issues:
        raise IncompatibleInputsError(validation.blocking_issues)
    truth = store.get_input(workspace_id, request.ground_truth_input_id)
    predictions = store.get_input(workspace_id, request.predictions_input_id)
    run_id = f"run-{uuid.uuid4().hex}"
    config = RunConfig(
        run_id=run_id,
        dataset_name=request.dataset_name,
        dataset_version=request.dataset_version,
        system_name=request.system_name,
        top_k=request.top_k,
        evaluator_versions={"retrieval": "deterministic-v1"},
        git_commit=git_commit,
    )
    snapshot = RunSnapshot(
        run_id=run_id,
        workspace_id=workspace_id,
        run_name=request.run_name,
        ground_truth_input_id=truth.input_id,
        ground_truth_content_sha256=truth.content_sha256,
        predictions_input_id=predictions.input_id,
        predictions_content_sha256=predictions.content_sha256,
        config=config,
        created_at=datetime.now(UTC),
    )
    # Recheck content at the final storage boundary; Task 5 also checks before execution.
    store.read_input_bytes(workspace_id, truth.input_id)
    store.read_input_bytes(workspace_id, predictions.input_id)
    store.save_run_snapshot(workspace_id, snapshot)
    return snapshot
