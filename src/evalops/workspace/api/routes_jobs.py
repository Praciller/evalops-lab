"""Safe job projections and revision-based SSE without private evaluator content."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from evalops.workspace.api.models import JobSummary
from evalops.workspace.application.runs import RetrievalRunService
from evalops.workspace.jobs.models import TERMINAL_STATES
from evalops.workspace.storage import WorkspaceStore

POLL_SECONDS = 0.2


def register_job_routes(
    app: FastAPI,
    store: WorkspaceStore,
    service: RetrievalRunService,
    require_session: Callable[[Request], None],
    require_mutation: Callable[[Request], None],
) -> None:
    @app.get("/api/v1/jobs/{job_id}", response_model=JobSummary)
    def get_job(request: Request, job_id: str) -> JobSummary:
        require_session(request)
        return JobSummary.from_record(store.find_job_record(job_id))

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobSummary)
    def cancel_job(request: Request, job_id: str) -> JobSummary:
        require_mutation(request)
        return JobSummary.from_record(service.cancel_job(job_id))

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=JobSummary, status_code=201)
    def retry_job(request: Request, job_id: str) -> JobSummary:
        require_mutation(request)
        original = store.find_job_record(job_id)
        try:
            record = service.retry_job(original.workspace_id, job_id)
        except ValueError as error:
            raise HTTPException(status_code=409) from error
        service.start()
        return JobSummary.from_record(record)

    @app.get("/api/v1/jobs/{job_id}/events")
    async def stream_job(request: Request, job_id: str) -> StreamingResponse:
        require_session(request)
        first = store.find_job_record(job_id)
        raw_last = request.headers.get("last-event-id")
        try:
            last_revision = int(raw_last) if raw_last is not None else -1
        except ValueError:
            last_revision = -1
        last_revision = max(-1, last_revision)

        async def stream() -> AsyncIterator[str]:
            current_revision = last_revision
            for _ in range(150):  # bounded stream lifetime; clients reconnect
                if await request.is_disconnected():
                    return
                job = store.get_job_record(first.workspace_id, first.job_id)
                if job.revision > current_revision:
                    summary = JobSummary.from_record(job)
                    payload = json.dumps(summary.model_dump(mode="json"), separators=(",", ":"))
                    yield f"id: {job.revision}\nevent: job\ndata: {payload}\n\n"
                    current_revision = job.revision
                if job.state in TERMINAL_STATES:
                    return
                await asyncio.sleep(POLL_SECONDS)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
