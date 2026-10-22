"""Constrained local retrieval run creation and safe summaries."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request

from evalops.workspace.api.models import (
    PairRequest,
    PairResponse,
    RunListResponse,
    RunSummary,
)
from evalops.workspace.application.runs import (
    CreateRetrievalRun,
    IncompatibleInputsError,
    RetrievalRunService,
    validate_retrieval_pair,
)
from evalops.workspace.ingestion.models import InputValidationError
from evalops.workspace.storage import WorkspaceStore


def register_run_routes(
    app: FastAPI,
    store: WorkspaceStore,
    service: RetrievalRunService,
    require_session: Callable[[Request], None],
    require_mutation: Callable[[Request], None],
) -> None:
    @app.post("/api/v1/workspaces/{workspace_id}/runs/validate", response_model=PairResponse)
    def validate_pair(request: Request, workspace_id: str, payload: PairRequest) -> PairResponse:
        require_mutation(request)
        report = validate_retrieval_pair(
            store,
            workspace_id,
            payload.ground_truth_input_id,
            payload.predictions_input_id,
        )
        return PairResponse(
            ground_truth_records=report.ground_truth_records,
            prediction_records=report.prediction_records,
            matching_query_count=report.matching_query_count,
            missing_prediction_count=len(report.missing_prediction_query_ids),
            extra_prediction_count=len(report.extra_prediction_query_ids),
            blocking_codes=[issue.code for issue in report.blocking_issues],
            warning_codes=[issue.code for issue in report.warnings],
        )

    @app.get("/api/v1/workspaces/{workspace_id}/runs", response_model=RunListResponse)
    def list_runs(request: Request, workspace_id: str) -> RunListResponse:
        require_session(request)
        latest_jobs = {}
        for job in sorted(
            store.list_job_records(workspace_id),
            key=lambda item: (item.created_at, item.job_id),
        ):
            latest_jobs[job.run_id] = job.job_id
        return RunListResponse(
            runs=[
                RunSummary.from_snapshot(snapshot).model_copy(
                    update={"job_id": latest_jobs.get(snapshot.run_id)}
                )
                for snapshot in store.list_run_snapshots(workspace_id)
            ]
        )

    @app.post("/api/v1/workspaces/{workspace_id}/runs", response_model=RunSummary, status_code=201)
    def create_run(request: Request, workspace_id: str, payload: CreateRetrievalRun) -> RunSummary:
        require_mutation(request)
        try:
            job = service.create_and_enqueue(workspace_id, payload)
        except IncompatibleInputsError as error:
            raise InputValidationError(
                "INCOMPATIBLE_INPUTS", "retrieval inputs are incompatible"
            ) from error
        service.start()
        return RunSummary.from_snapshot(
            store.get_run_snapshot(workspace_id, job.run_id)
        ).model_copy(update={"job_id": job.job_id})

    @app.get("/api/v1/workspaces/{workspace_id}/runs/{run_id}", response_model=RunSummary)
    def get_run(request: Request, workspace_id: str, run_id: str) -> RunSummary:
        require_session(request)
        snapshot = store.get_run_snapshot(workspace_id, run_id)
        jobs = sorted(
            (job for job in store.list_job_records(workspace_id) if job.run_id == run_id),
            key=lambda item: (item.created_at, item.job_id),
        )
        latest_job_id = jobs[-1].job_id if jobs else None
        has_complete = any(job.state == "COMPLETE" for job in jobs)
        if not has_complete:
            return RunSummary.from_snapshot(snapshot).model_copy(update={"job_id": latest_job_id})
        result, provenance = store.get_run_artifacts(workspace_id, run_id)
        failures: dict[str, int] = {}
        for item in result.failures:
            failures[item.category.value] = failures.get(item.category.value, 0) + 1
        return RunSummary.from_snapshot(snapshot, metrics=result.metrics).model_copy(
            update={
                "job_id": latest_job_id,
                "failure_counts": failures,
                "result_sha256": provenance.result_sha256,
                "evalops_version": provenance.evalops_version,
            }
        )
