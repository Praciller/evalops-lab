"""Authenticated, same-origin FastAPI shell for local Workspace metadata."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from evalops.workspace.api.models import (
    BootstrapRequest,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    SessionInfo,
    WorkspaceListResponse,
    WorkspaceNameRequest,
    WorkspaceSummary,
)
from evalops.workspace.api.routes_comparisons import register_comparison_routes
from evalops.workspace.api.routes_exports import register_export_routes
from evalops.workspace.api.routes_inputs import register_input_routes
from evalops.workspace.api.routes_jobs import register_job_routes
from evalops.workspace.api.routes_runs import register_run_routes
from evalops.workspace.application.runs import RetrievalRunService
from evalops.workspace.ingestion.models import InputValidationError
from evalops.workspace.security import (
    BootstrapSessionManager,
    UnauthenticatedError,
    WorkspaceOrigin,
    WorkspaceSecurityError,
    validate_host_header,
    validate_mutating_origin,
)
from evalops.workspace.storage import (
    UnknownComparisonError,
    UnknownInputError,
    UnknownJobError,
    UnknownRunError,
    UnknownWorkspaceError,
    WorkspaceStorageError,
    WorkspaceStore,
)

SESSION_COOKIE_NAME = "evalops_workspace_session"
_CSP = (
    "default-src 'self'; connect-src 'self'; object-src 'none';"
    " frame-ancestors 'none'; base-uri 'none'"
)


def create_workspace_app(
    store: WorkspaceStore,
    session_manager: BootstrapSessionManager,
    origin: WorkspaceOrigin,
    static_dir: Path | None = None,
) -> FastAPI:
    """Create an isolated application instance with injected storage/security state."""

    store.initialize()
    run_service = RetrievalRunService(store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        run_service.start()
        try:
            yield
        finally:
            run_service.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="EvalOps Local Workspace",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def local_request_security(request: Request, call_next: Any) -> Response:
        try:
            validate_host_header(request.headers.get("host", ""), origin)
        except WorkspaceSecurityError as error:
            response = _error_response(error.code, str(error), 400)
        else:
            # FastAPI parses UploadFile multipart bodies before entering the route.
            # Check authorization here, before any unauthenticated upload is spooled.
            is_file_upload = (
                request.method == "POST"
                and request.url.path.startswith("/api/v1/workspaces/")
                and request.url.path.endswith(("/inputs/upload", "/inputs/csv"))
            )
            is_export_mutation = (
                request.method == "POST"
                and request.url.path.startswith("/api/v1/workspaces/")
                and request.url.path.endswith(("/exports/preview", "/exports/confirm"))
            )
            if is_file_upload or is_export_mutation:
                try:
                    _require_mutation(request, session_manager, origin)
                except WorkspaceSecurityError as error:
                    response = _error_response(
                        error.code,
                        str(error),
                        401 if isinstance(error, UnauthenticatedError) else 403,
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
        _add_security_headers(response)
        return response

    @app.exception_handler(WorkspaceSecurityError)
    async def security_error_handler(_: Request, error: WorkspaceSecurityError) -> JSONResponse:
        status_code = 401 if error.code in {"invalid_bootstrap", "unauthenticated"} else 403
        return _error_response(error.code, str(error), status_code)

    @app.exception_handler(InputValidationError)
    async def input_error_handler(_: Request, error: InputValidationError) -> JSONResponse:
        return _error_response(error.code, str(error), 422)

    @app.exception_handler(WorkspaceStorageError)
    async def storage_error_handler(_: Request, error: WorkspaceStorageError) -> JSONResponse:
        status_code = (
            404
            if isinstance(
                error,
                (
                    UnknownWorkspaceError,
                    UnknownInputError,
                    UnknownRunError,
                    UnknownJobError,
                    UnknownComparisonError,
                ),
            )
            else 500
        )
        return _error_response("workspace_storage_error", str(error), status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error_response("invalid_request", "request validation failed", 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 409:
            return _error_response("invalid_job_state", "job operation is not available", 409)
        return _error_response("not_found", "resource not found", error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, __: Exception) -> JSONResponse:
        return _error_response("internal_error", "workspace request failed", 500)

    @app.post("/api/v1/session/bootstrap", response_model=SessionInfo)
    async def bootstrap(
        request: Request, response: Response, payload: BootstrapRequest
    ) -> SessionInfo:
        _require_origin(request, origin)
        session_id = session_manager.consume_bootstrap_nonce(payload.nonce)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return SessionInfo(authenticated=True)

    @app.get("/api/v1/session", response_model=SessionInfo)
    async def session_info(request: Request) -> SessionInfo:
        _require_session(request, session_manager)
        return SessionInfo(authenticated=True)

    @app.get("/api/v1/workspaces", response_model=WorkspaceListResponse)
    async def list_workspaces(request: Request) -> WorkspaceListResponse:
        _require_session(request, session_manager)
        return WorkspaceListResponse(
            workspaces=[WorkspaceSummary.from_record(record) for record in store.list_workspaces()]
        )

    @app.post("/api/v1/workspaces", response_model=WorkspaceSummary, status_code=201)
    async def create_workspace(request: Request, payload: WorkspaceNameRequest) -> WorkspaceSummary:
        _require_mutation(request, session_manager, origin)
        return WorkspaceSummary.from_record(store.create_workspace(payload.display_name))

    @app.get("/api/v1/workspaces/{workspace_id}", response_model=WorkspaceSummary)
    async def get_workspace(request: Request, workspace_id: str) -> WorkspaceSummary:
        _require_session(request, session_manager)
        return WorkspaceSummary.from_record(store.get_workspace(workspace_id))

    @app.patch("/api/v1/workspaces/{workspace_id}", response_model=WorkspaceSummary)
    async def rename_workspace(
        request: Request, workspace_id: str, payload: WorkspaceNameRequest
    ) -> WorkspaceSummary:
        _require_mutation(request, session_manager, origin)
        return WorkspaceSummary.from_record(
            store.rename_workspace(workspace_id, payload.display_name)
        )

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        _require_session(request, session_manager)
        return HealthResponse(status="ok")

    def require_read(request: Request) -> None:
        _require_session(request, session_manager)

    def require_write(request: Request) -> None:
        _require_mutation(request, session_manager, origin)

    register_input_routes(app, store, require_read, require_write)
    register_run_routes(app, store, run_service, require_read, require_write)
    register_job_routes(app, store, run_service, require_read, require_write)
    register_comparison_routes(app, store, require_read, require_write)
    register_export_routes(app, store, require_read, require_write)

    if static_dir is not None:
        static_root = static_dir.resolve()
        if static_root.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=static_root / "assets", check_dir=False),
                name="workspace-assets",
            )

        @app.get("/{path:path}")
        async def serve_workspace(path: str) -> Response:
            if path.startswith("api/"):
                raise StarletteHTTPException(status_code=404)
            candidate = (static_root / path).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                raise StarletteHTTPException(status_code=404) from None
            if candidate.is_file():
                return FileResponse(candidate)
            index_path = static_root / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)
            raise StarletteHTTPException(status_code=404)

    return app


def _require_session(request: Request, manager: BootstrapSessionManager) -> None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None or not manager.validate_session(session_id):
        raise UnauthenticatedError("request is not authenticated")
    return None


def _require_origin(request: Request, origin: WorkspaceOrigin) -> None:
    validate_mutating_origin(request.headers.get("origin"), origin)


def _require_mutation(
    request: Request, manager: BootstrapSessionManager, origin: WorkspaceOrigin
) -> None:
    _require_session(request, manager)
    _require_origin(request, origin)


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, field=None, retryable=False)
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _add_security_headers(response: Response) -> None:
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
