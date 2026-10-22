"""Real authenticated local retrieval API and safe persisted-state SSE contracts."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from evalops.workspace.api.app import create_workspace_app
from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
from evalops.workspace.storage import WorkspaceStore

GT = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
PRED = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
HEADERS = {"Host": "127.0.0.1:8123", "Origin": "http://127.0.0.1:8123"}


@pytest.fixture
def ctx(tmp_path: Path) -> tuple[TestClient, WorkspaceStore, str, BootstrapSessionManager]:
    root = tmp_path / "private"
    store = WorkspaceStore(root)
    manager = BootstrapSessionManager(bootstrap_nonce="SENSITIVE_BOOTSTRAP")
    app = create_workspace_app(store, manager, WorkspaceOrigin(host="127.0.0.1", port=8123))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session/bootstrap",
            json={"nonce": "SENSITIVE_BOOTSTRAP"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        created = client.post(
            "/api/v1/workspaces", json={"display_name": "Retrieval"}, headers=HEADERS
        )
        assert created.status_code == 201
        yield client, store, created.json()["workspace_id"], manager


def _upload(
    client: TestClient, ws: str, kind: str, data: bytes, filename: str = "input.jsonl"
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{ws}/inputs/upload",
        headers=HEADERS,
        data={"kind": kind},
        files={"file": (filename, data, "application/x-ndjson")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pair(client: TestClient, ws: str) -> tuple[dict, dict]:
    return (
        _upload(client, ws, "retrieval_ground_truth", GT),
        _upload(client, ws, "retrieval_predictions", PRED),
    )


def _run(client: TestClient, ws: str, truth: dict, pred: dict) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{ws}/runs",
        headers=HEADERS,
        json={
            "run_name": "Local test",
            "ground_truth_input_id": truth["input_id"],
            "predictions_input_id": pred["input_id"],
            "top_k": 2,
            "system_name": "fixture",
            "dataset_name": "synthetic",
            "dataset_version": "v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait(client: TestClient, job_id: str, state: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200, response.text
        job = response.json()
        if job["state"] == state:
            return job
        threading.Event().wait(0.02)
    pytest.fail(f"job did not become {state}")


def test_upload_list_get_and_private_path_not_leaked(ctx: tuple) -> None:
    client, store, ws, manager = ctx
    truth = _upload(client, ws, "retrieval_ground_truth", GT)
    assert truth["kind"] == "retrieval_ground_truth"
    assert truth["record_count"] == 1
    assert "source_path" not in truth
    assert "stored_relative_path" not in truth
    assert "SENSITIVE_BOOTSTRAP" not in json.dumps(truth)
    by_id = client.get(f"/api/v1/workspaces/{ws}/inputs/{truth['input_id']}", headers=HEADERS)
    listing = client.get(f"/api/v1/workspaces/{ws}/inputs", headers=HEADERS)
    assert by_id.status_code == listing.status_code == 200
    assert by_id.json() == truth
    assert listing.json()["inputs"] == [truth]
    assert str(store.root) not in listing.text
    assert manager.bootstrap_nonce not in listing.text


def test_reference_and_csv_mapping_are_safe(ctx: tuple, tmp_path: Path) -> None:
    client, _, ws, _ = ctx
    source = tmp_path / "PRIVATE-TOKEN-predictions.jsonl"
    source.write_bytes(PRED)
    response = client.post(
        f"/api/v1/workspaces/{ws}/inputs/reference",
        headers=HEADERS,
        json={"kind": "retrieval_predictions", "path": str(source)},
    )
    assert response.status_code == 201, response.text
    assert "PRIVATE-TOKEN" not in response.text
    assert str(source) not in response.text
    assert response.json()["source_mode"] == "referenced"
    csv_response = client.post(
        f"/api/v1/workspaces/{ws}/inputs/csv",
        headers=HEADERS,
        data={
            "kind": "retrieval_ground_truth",
            "query_id_column": "query",
            "document_ids_column": "docs",
            "document_ids_delimiter": "|",
        },
        files={"file": ("converted.csv", b"query,docs\nq1,d1|d2\n", "text/csv")},
    )
    assert csv_response.status_code == 201, csv_response.text
    assert csv_response.json()["record_count"] == 1
    assert "csv" not in csv_response.json()["source_mode"]


def test_validate_enqueue_list_get_and_sse_terminal_revision(ctx: tuple) -> None:
    client, _, ws, _ = ctx
    truth, pred = _pair(client, ws)
    validation = client.post(
        f"/api/v1/workspaces/{ws}/runs/validate",
        headers=HEADERS,
        json={
            "ground_truth_input_id": truth["input_id"],
            "predictions_input_id": pred["input_id"],
        },
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["matching_query_count"] == 1
    assert not validation.json()["blocking_codes"]
    assert "q1" not in validation.text
    run = _run(client, ws, truth, pred)
    assert run["job_id"].startswith("job-")
    job = _wait(client, run["job_id"], "COMPLETE")
    assert job["revision"] >= 5
    listed = client.get(f"/api/v1/workspaces/{ws}/runs", headers=HEADERS)
    fetched = client.get(f"/api/v1/workspaces/{ws}/runs/{run['run_id']}", headers=HEADERS)
    assert listed.status_code == fetched.status_code == 200
    assert len(listed.json()["runs"]) == 1
    assert "hit_rate_at_2" in fetched.json()["metrics"]
    assert "details" not in fetched.text
    with client.stream("GET", f"/api/v1/jobs/{job['job_id']}/events", headers=HEADERS) as events:
        assert events.status_code == 200
        payload = events.read().decode("utf-8")
    assert f"id: {job['revision']}\n" in payload
    assert "event: job\n" in payload
    assert "data: " in payload
    assert "q1" not in payload
    assert "relevant_document_ids" not in payload
    with client.stream(
        "GET",
        f"/api/v1/jobs/{job['job_id']}/events",
        headers={**HEADERS, "Last-Event-ID": str(job["revision"])},
    ) as events:
        assert events.read() == b""


def test_session_mutation_origin_and_id_rejection(ctx: tuple) -> None:
    client, _, ws, _ = ctx
    path = f"/api/v1/workspaces/{ws}/inputs/upload"
    no_cookie_client = TestClient(client.app)
    no_cookie = no_cookie_client.post(
        path,
        headers=HEADERS,
        data={"kind": "retrieval_ground_truth"},
        files={"file": ("input.jsonl", GT)},
    )
    assert no_cookie.status_code == 401
    bad_origin = client.post(
        path,
        headers={**HEADERS, "Origin": "https://evil.example"},
        data={"kind": "retrieval_ground_truth"},
        files={"file": ("input.jsonl", GT)},
    )
    assert bad_origin.status_code == 403
    bad_host = client.get(f"/api/v1/workspaces/{ws}/inputs", headers={"Host": "evil.example"})
    assert bad_host.status_code == 400
    truth = _upload(client, ws, "retrieval_ground_truth", GT)
    other = client.post(
        "/api/v1/workspaces", headers=HEADERS, json={"display_name": "Other"}
    ).json()["workspace_id"]
    cross = client.get(f"/api/v1/workspaces/{other}/inputs/{truth['input_id']}", headers=HEADERS)
    assert cross.status_code == 404
    assert "source_path" not in cross.text
    assert client.get("/api/v1/jobs/job-" + "f" * 32, headers=HEADERS).status_code == 404
    assert (
        client.get(f"/api/v1/workspaces/{ws}/runs/run-{'f' * 32}", headers=HEADERS).status_code
        == 404
    )


def test_bad_inputs_fail_with_safe_error_and_no_paths(ctx: tuple) -> None:
    client, _, ws, _ = ctx
    bad = client.post(
        f"/api/v1/workspaces/{ws}/inputs/upload",
        headers=HEADERS,
        data={"kind": "retrieval_ground_truth"},
        files={"file": ("secret.jsonl", b"{invalid json}")},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "INVALID_JSONL"
    assert "invalid json" not in bad.text
    assert "secret.jsonl" not in bad.text


def test_queued_cancel_and_retry_api(ctx: tuple) -> None:
    client, store, ws, _ = ctx
    truth, pred = _pair(client, ws)
    # Use persisted CANCELLED job to prove the public retry contract deterministically.
    from evalops.workspace.application.runs import CreateRetrievalRun, create_retrieval_run
    from evalops.workspace.jobs.models import JobRecord

    snapshot = create_retrieval_run(
        store,
        ws,
        CreateRetrievalRun(
            run_name="Pending",
            ground_truth_input_id=truth["input_id"],
            predictions_input_id=pred["input_id"],
            top_k=2,
            system_name="fixture",
            dataset_name="synthetic",
            dataset_version="v1",
        ),
    )
    queued = JobRecord.queued(ws, snapshot.run_id)
    store.save_job_record(queued)
    cancelled = client.post(f"/api/v1/jobs/{queued.job_id}/cancel", headers=HEADERS)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"
    retry = client.post(f"/api/v1/jobs/{queued.job_id}/retry", headers=HEADERS)
    assert retry.status_code == 201, retry.text
    assert retry.json()["job_id"] != queued.job_id
    _wait(client, retry.json()["job_id"], "COMPLETE")
    assert store.get_job_record(ws, queued.job_id).state == "CANCELLED"


def test_mutated_reference_blocks_validation_and_run_creation_without_leak(
    ctx: tuple,
    tmp_path: Path,
) -> None:
    client, _, ws, _ = ctx
    truth = _upload(client, ws, "retrieval_ground_truth", GT)
    source = tmp_path / "PRIVATE-secrets-predictions.jsonl"
    source.write_bytes(PRED)
    response = client.post(
        f"/api/v1/workspaces/{ws}/inputs/reference",
        headers=HEADERS,
        json={"kind": "retrieval_predictions", "path": str(source)},
    )
    assert response.status_code == 201
    pred = response.json()
    source.write_bytes(b'{"query_id":"q1","retrieved_document_ids":["changed"]}\n')
    validation = client.post(
        f"/api/v1/workspaces/{ws}/runs/validate",
        headers=HEADERS,
        json={
            "ground_truth_input_id": truth["input_id"],
            "predictions_input_id": pred["input_id"],
        },
    )
    assert validation.status_code == 200
    assert "INVALID_INPUT" in validation.json()["blocking_codes"]
    assert "PRIVATE-secrets" not in validation.text

    request = client.post(
        f"/api/v1/workspaces/{ws}/runs",
        headers=HEADERS,
        json={
            "run_name": "Must fail",
            "ground_truth_input_id": truth["input_id"],
            "predictions_input_id": pred["input_id"],
            "top_k": 2,
            "system_name": "fixture",
            "dataset_name": "synthetic",
            "dataset_version": "v1",
        },
    )
    assert request.status_code == 422
    assert request.json()["error"]["code"] == "INCOMPATIBLE_INPUTS"
    assert str(source) not in request.text
    assert client.get(f"/api/v1/workspaces/{ws}/runs", headers=HEADERS).json() == {"runs": []}


def test_completed_artifact_mutation_returns_error_instead_of_success(
    ctx: tuple,
    tmp_path: Path,
) -> None:
    client, store, ws, _ = ctx
    truth, pred = _pair(client, ws)
    run = _run(client, ws, truth, pred)
    _wait(client, run["job_id"], "COMPLETE")
    result = client.get(f"/api/v1/workspaces/{ws}/runs/{run['run_id']}", headers=HEADERS)
    assert result.status_code == 200 and result.json()["metrics"]
    path = store._run_config_path(ws, run["run_id"]).parent / "result.json"
    path.write_bytes(b'{"fake":"result"}\n')
    after = client.get(f"/api/v1/workspaces/{ws}/runs/{run['run_id']}", headers=HEADERS)
    assert after.status_code == 500
    assert "metrics" not in after.text
    assert "result.json" not in after.text


def test_invalid_csv_mapping_and_retry_conflict_are_safe(ctx: tuple) -> None:
    client, _, ws, _ = ctx
    invalid = client.post(
        f"/api/v1/workspaces/{ws}/inputs/csv",
        headers=HEADERS,
        data={
            "kind": "retrieval_ground_truth",
            "query_id_column": "q",
            "document_ids_column": "doc",
            "document_ids_delimiter": "||",
        },
        files={"file": ("input.csv", b"q,doc\nq1,d1\n")},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_MAPPING"
    truth, pred = _pair(client, ws)
    run = _run(client, ws, truth, pred)
    _wait(client, run["job_id"], "COMPLETE")
    retry = client.post(f"/api/v1/jobs/{run['job_id']}/retry", headers=HEADERS)
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "invalid_job_state"


def test_terminal_sse_reconnect_with_older_revision_returns_latest(
    ctx: tuple,
) -> None:
    client, _, ws, _ = ctx
    truth, pred = _pair(client, ws)
    run = _run(client, ws, truth, pred)
    job = _wait(client, run["job_id"], "COMPLETE")
    with client.stream(
        "GET",
        f"/api/v1/jobs/{job['job_id']}/events",
        headers={**HEADERS, "Last-Event-ID": str(job["revision"] - 1)},
    ) as streamed:
        text = streamed.read().decode("utf-8")
    assert f"id: {job['revision']}\n" in text
    assert '"state":"COMPLETE"' in text
    assert "PRIVATE" not in text
    assert '"details"' not in text
    assert "retrieved_document_ids" not in text
