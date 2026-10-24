"""Fail-closed authenticated local baseline, comparison and Failure Explorer APIs."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from evalops.failures.taxonomy import FailureCategory
from evalops.workspace.api.models import (
    BaselineResponse,
    ComparisonConflictResponse,
    ComparisonFailuresResponse,
    ComparisonListResponse,
    CreateComparisonRequest,
    ErrorDetail,
    ErrorResponse,
    SetBaselineRequest,
)
from evalops.workspace.application.comparisons import (
    ComparisonService,
    IncompatibleComparisonError,
)
from evalops.workspace.comparison.models import ComparisonRecord, FailureTransition
from evalops.workspace.storage import (
    UnknownComparisonError,
    UnknownRunError,
    WorkspaceStorageError,
    WorkspaceStore,
)


def _conflict(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, field=None, retryable=False)
        ).model_dump(mode="json"),
    )


def register_comparison_routes(
    app: FastAPI,
    store: WorkspaceStore,
    require_session: Callable[[Request], None],
    require_mutation: Callable[[Request], None],
) -> None:
    service = ComparisonService(store)

    @app.get(
        "/api/v1/workspaces/{workspace_id}/baseline",
        response_model=BaselineResponse,
    )
    def get_baseline(request: Request, workspace_id: str) -> BaselineResponse:
        require_session(request)
        return BaselineResponse(baseline=service.get_baseline(workspace_id))

    @app.put(
        "/api/v1/workspaces/{workspace_id}/baseline",
        response_model=BaselineResponse,
        responses={409: {"model": ErrorResponse}},
    )
    def put_baseline(
        request: Request, workspace_id: str, payload: SetBaselineRequest
    ) -> BaselineResponse | JSONResponse:
        require_mutation(request)
        previous = service.get_baseline(workspace_id)
        if (
            previous is not None
            and previous.run_id != payload.run_id
            and not payload.confirm_replace
        ):
            return _conflict(
                "baseline_replace_confirmation_required",
                "replacing an existing baseline requires explicit confirmation",
            )
        try:
            state = service.set_baseline(workspace_id, payload.run_id)
        except UnknownRunError:
            raise
        except WorkspaceStorageError as error:
            if str(error) == "completed run evidence is unavailable":
                return _conflict(
                    "invalid_baseline_run",
                    "baseline must reference one completed and verified run",
                )
            raise
        return BaselineResponse(baseline=state.baseline)

    @app.get(
        "/api/v1/workspaces/{workspace_id}/comparisons",
        response_model=ComparisonListResponse,
    )
    def list_comparisons(request: Request, workspace_id: str) -> ComparisonListResponse:
        require_session(request)
        return ComparisonListResponse(comparisons=store.list_comparison_records(workspace_id))

    @app.post(
        "/api/v1/workspaces/{workspace_id}/comparisons",
        response_model=ComparisonRecord,
        status_code=201,
        responses={409: {"model": ComparisonConflictResponse}},
    )
    def post_comparison(
        request: Request, workspace_id: str, payload: CreateComparisonRequest
    ) -> ComparisonRecord | JSONResponse:
        require_mutation(request)
        try:
            return service.create_comparison(
                workspace_id, payload.candidate_run_id, mode=payload.mode
            )
        except IncompatibleComparisonError as error:
            return JSONResponse(
                status_code=409,
                content=ComparisonConflictResponse(
                    error=ErrorDetail(
                        code="non_comparable",
                        message="canonical comparison requires compatible run populations",
                        field=None,
                        retryable=False,
                    ),
                    compatibility=error.compatibility,
                ).model_dump(mode="json"),
            )
        except WorkspaceStorageError as error:
            if str(error) == "no pinned workspace baseline":
                return _conflict("baseline_not_set", "pin a completed baseline first")
            raise
        except ValueError as error:
            if str(error) == "a run cannot be compared with itself":
                return _conflict("self_comparison", "baseline and candidate runs must differ")
            raise

    @app.get(
        "/api/v1/workspaces/{workspace_id}/comparisons/{comparison_id}",
        response_model=ComparisonRecord,
    )
    def get_comparison(request: Request, workspace_id: str, comparison_id: str) -> ComparisonRecord:
        require_session(request)
        return store.get_comparison_record(workspace_id, comparison_id)

    @app.get(
        "/api/v1/workspaces/{workspace_id}/comparisons/{comparison_id}/failures",
        response_model=ComparisonFailuresResponse,
        responses={409: {"model": ErrorResponse}},
    )
    def list_failure_transitions(
        request: Request,
        workspace_id: str,
        comparison_id: str,
        transition: FailureTransition | None = None,
        category: FailureCategory | None = None,
        query_id: str | None = Query(default=None, min_length=1, max_length=200),
        exact: bool = True,
    ) -> ComparisonFailuresResponse | JSONResponse:
        require_session(request)
        try:
            artifact = store.get_comparison_failures(workspace_id, comparison_id)
        except UnknownComparisonError:
            raise
        except WorkspaceStorageError as error:
            if str(error) == "comparison failure evidence is unavailable":
                return _conflict(
                    "failure_evidence_unavailable",
                    "per-query comparison transitions are unavailable for these operands",
                )
            raise
        filtered = artifact.transitions
        if transition is not None:
            filtered = [item for item in filtered if item.transition == transition]
        if category is not None:
            filtered = [
                item
                for item in filtered
                if item.baseline_category == category or item.candidate_category == category
            ]
        if query_id is not None:
            filtered = [
                item
                for item in filtered
                if (item.query_id == query_id if exact else query_id in item.query_id)
            ]
        return ComparisonFailuresResponse(
            comparison_id=comparison_id,
            total_count=len(filtered),
            transitions=filtered,
        )
