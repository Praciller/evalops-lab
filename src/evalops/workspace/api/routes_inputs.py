"""Authenticated local input registration; never serialize referenced file paths."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from pydantic import ValidationError

from evalops.workspace.api.models import InputListResponse, InputSummary, ReferenceInputRequest
from evalops.workspace.ingestion.models import (
    MAX_INPUT_BYTES,
    CsvMapping,
    InputKind,
    InputValidationError,
)
from evalops.workspace.ingestion.service import (
    register_imported_csv,
    register_imported_jsonl,
    register_referenced_jsonl,
)
from evalops.workspace.storage import WorkspaceStore


def register_input_routes(
    app: FastAPI,
    store: WorkspaceStore,
    require_session: Callable[[Request], None],
    require_mutation: Callable[[Request], None],
) -> None:
    @app.get("/api/v1/workspaces/{workspace_id}/inputs", response_model=InputListResponse)
    def list_inputs(request: Request, workspace_id: str) -> InputListResponse:
        require_session(request)
        return InputListResponse(
            inputs=[
                InputSummary.from_manifest(manifest) for manifest in store.list_inputs(workspace_id)
            ]
        )

    @app.get("/api/v1/workspaces/{workspace_id}/inputs/{input_id}", response_model=InputSummary)
    def get_input(request: Request, workspace_id: str, input_id: str) -> InputSummary:
        require_session(request)
        return InputSummary.from_manifest(store.get_input(workspace_id, input_id))

    @app.post(
        "/api/v1/workspaces/{workspace_id}/inputs/upload",
        response_model=InputSummary,
        status_code=201,
    )
    async def upload_input(
        request: Request,
        workspace_id: str,
        kind: Annotated[InputKind, Form()],
        file: Annotated[UploadFile, File()],
    ) -> InputSummary:
        require_mutation(request)
        data = await file.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise InputValidationError("INPUT_TOO_LARGE", "input exceeds 10 MiB limit")
        return InputSummary.from_manifest(
            register_imported_jsonl(
                store,
                workspace_id,
                kind=kind,
                data=data,
                source_filename=file.filename or "",
            ).manifest
        )

    @app.post(
        "/api/v1/workspaces/{workspace_id}/inputs/reference",
        response_model=InputSummary,
        status_code=201,
    )
    def reference_input(
        request: Request, workspace_id: str, payload: ReferenceInputRequest
    ) -> InputSummary:
        require_mutation(request)
        return InputSummary.from_manifest(
            register_referenced_jsonl(
                store,
                workspace_id,
                kind=payload.kind,
                source=Path(payload.path),
            ).manifest
        )

    @app.post(
        "/api/v1/workspaces/{workspace_id}/inputs/csv", response_model=InputSummary, status_code=201
    )
    async def csv_input(
        request: Request,
        workspace_id: str,
        kind: Annotated[InputKind, Form()],
        query_id_column: Annotated[str, Form()],
        document_ids_column: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        document_ids_delimiter: Annotated[str, Form()] = "|",
    ) -> InputSummary:
        require_mutation(request)
        data = await file.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise InputValidationError("INPUT_TOO_LARGE", "input exceeds 10 MiB limit")
        try:
            mapping = CsvMapping(
                query_id_column=query_id_column,
                document_ids_column=document_ids_column,
                document_ids_delimiter=document_ids_delimiter,
            )
        except ValidationError as error:
            raise InputValidationError(
                "INVALID_MAPPING", "CSV column mapping is invalid"
            ) from error
        return InputSummary.from_manifest(
            register_imported_csv(
                store,
                workspace_id,
                kind=kind,
                data=data,
                source_filename=file.filename or "",
                mapping=mapping,
            ).manifest
        )
