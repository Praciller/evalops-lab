"""Authenticated, same-origin two-step private-to-public export API.

A successful local export is an owner-selected filesystem write, never a
GitHub, Pages, repository or cloud publication.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from evalops.workspace.api.models import (
    ErrorDetail,
    ErrorResponse,
    ExportListResponse,
    ExportPreviewRequest,
)
from evalops.workspace.application.exports import ExportService
from evalops.workspace.export.models import (
    ConfirmExportRequest,
    ExportManifest,
    ExportPreview,
)
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore


def _safe_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, field=None, retryable=False)
        ).model_dump(mode="json"),
    )


def register_export_routes(
    app: FastAPI,
    store: WorkspaceStore,
    require_session: Callable[[Request], None],
    require_mutation: Callable[[Request], None],
) -> None:
    service = ExportService(store)

    @app.post(
        "/api/v1/workspaces/{workspace_id}/exports/preview",
        response_model=ExportPreview,
        responses={422: {"model": ErrorResponse}},
    )
    def create_export_preview(
        request: Request, workspace_id: str, payload: ExportPreviewRequest
    ) -> ExportPreview | JSONResponse:
        require_mutation(request)
        store.get_workspace(workspace_id)
        if not payload.source_id.startswith(f"{payload.source_type}-"):
            return _safe_error(422, "invalid_source_type", "source type does not match source ID")
        try:
            if payload.source_type == "run":
                return service.preview_run(workspace_id, payload.source_id, payload.classification)
            return service.preview_comparison(
                workspace_id, payload.source_id, payload.classification
            )
        except (WorkspaceStorageError, ValueError):
            return _safe_error(
                409, "source_evidence_unavailable", "selected local evidence is unavailable"
            )

    @app.post(
        "/api/v1/workspaces/{workspace_id}/exports/confirm",
        response_model=ExportManifest,
        status_code=201,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def confirm_export(
        request: Request, workspace_id: str, payload: ConfirmExportRequest
    ) -> ExportManifest | JSONResponse:
        require_mutation(request)
        store.get_workspace(workspace_id)
        try:
            return service.confirm(workspace_id, payload)
        except LookupError:
            return _safe_error(
                409, "export_preview_expired", "export preview is unavailable or expired"
            )
        except ValueError as error:
            reason = str(error)
            if reason == "source changed since export preview":
                return _safe_error(
                    409, "export_source_changed", "source changed; create a new preview"
                )
            if reason == "export destination already exists":
                return _safe_error(
                    409, "export_destination_exists", "selected output already exists"
                )
            return _safe_error(
                422, "export_destination_invalid", "selected export destination is invalid"
            )
        except OSError:
            return _safe_error(
                500,
                "export_write_failed",
                "export could not be written to the selected destination",
            )
        except WorkspaceStorageError:
            return _safe_error(
                500, "export_manifest_failed", "private export history could not be stored"
            )

    @app.get(
        "/api/v1/workspaces/{workspace_id}/exports",
        response_model=ExportListResponse,
    )
    def get_export_history(request: Request, workspace_id: str) -> ExportListResponse:
        require_session(request)
        return ExportListResponse(exports=store.list_export_manifests(workspace_id))
