"""Phase 6.3 Task 6 authenticated comparison, baseline and private failure APIs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evalops.workspace.api.app import create_workspace_app
from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
from evalops.workspace.storage import WorkspaceStore

HEADERS = {"Host": "127.0.0.1:8123", "Origin": "http://127.0.0.1:8123"}
GT = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
GT_OTHER = b'{"query_id":"q2","relevant_document_ids":["d2"]}\n'
GOOD = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
BAD = b'{"query_id":"q1","retrieved_document_ids":["d2"]}\n'


@pytest.fixture
def ctx(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "private")
    auth = BootstrapSessionManager(bootstrap_nonce="SECRET_NONCE")
    app = create_workspace_app(store, auth, WorkspaceOrigin(host="127.0.0.1", port=8123))
    with TestClient(app) as client:
        session = client.post(
            "/api/v1/session/bootstrap", headers=HEADERS, json={"nonce": "SECRET_NONCE"}
        )
        assert session.status_code == 200
        ws = client.post(
            "/api/v1/workspaces", headers=HEADERS, json={"display_name": "Private"}
        ).json()["workspace_id"]
        yield client, store, ws


def _create_run(
    client: TestClient,
    ws: str,
    *,
    ground_truth: bytes = GT,
    predictions: bytes = GOOD,
    top_k: int = 1,
) -> str:
    ids = []
    for kind, data in (
        ("retrieval_ground_truth", ground_truth),
        ("retrieval_predictions", predictions),
    ):
        created = client.post(
            f"/api/v1/workspaces/{ws}/inputs/upload",
            headers=HEADERS,
            data={"kind": kind},
            files={"file": ("source.jsonl", data)},
        )
        assert created.status_code == 201, created.text
        ids.append(created.json()["input_id"])
    response = client.post(
        f"/api/v1/workspaces/{ws}/runs",
        headers=HEADERS,
        json={
            "run_name": "Comparison test",
            "ground_truth_input_id": ids[0],
            "predictions_input_id": ids[1],
            "top_k": top_k,
            "system_name": "local",
            "dataset_name": "dataset",
            "dataset_version": "v1",
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()["job_id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        state = client.get(f"/api/v1/jobs/{job}", headers=HEADERS).json()["state"]
        if state == "COMPLETE":
            return response.json()["run_id"]
        if state in {"FAILED", "INTERRUPTED", "CANCELLED"}:
            pytest.fail(f"job state {state}")
        time.sleep(0.02)
    pytest.fail("timed out awaiting local run")


def _pin(client: TestClient, ws: str, run_id: str, *, confirm: bool = False):
    return client.put(
        f"/api/v1/workspaces/{ws}/baseline",
        headers=HEADERS,
        json={"run_id": run_id, "confirm_replace": confirm},
    )


def _compare(client: TestClient, ws: str, run_id: str, mode: str = "CANONICAL"):
    return client.post(
        f"/api/v1/workspaces/{ws}/comparisons",
        headers=HEADERS,
        json={"candidate_run_id": run_id, "mode": mode},
    )


def test_baseline_requires_owned_completed_run_and_explicit_repin(ctx) -> None:
    client, store, ws = ctx
    path = f"/api/v1/workspaces/{ws}/baseline"
    assert client.get(path, headers=HEADERS).json() == {"baseline": None}
    absent = _pin(client, ws, "run-" + "f" * 32)
    assert absent.status_code == 404
    assert client.get(path, headers=HEADERS).json() == {"baseline": None}

    first = _create_run(client, ws)
    second = _create_run(client, ws, predictions=BAD)
    pinned = _pin(client, ws, first)
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["baseline"]["run_id"] == first
    assert len(pinned.json()["baseline"]["result_sha256"]) == 64
    refused = _pin(client, ws, second)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "baseline_replace_confirmation_required"
    assert store.get_workspace_state(ws).baseline.run_id == first
    accepted = _pin(client, ws, second, confirm=True)
    assert accepted.status_code == 200
    assert accepted.json()["baseline"]["run_id"] == second
    assert "SENSITIVE" not in accepted.text


def test_comparison_api_canonical_result_and_filtered_private_failures(ctx) -> None:
    client, store, ws = ctx
    baseline = _create_run(client, ws, predictions=GOOD)
    candidate = _create_run(client, ws, predictions=BAD)
    root = f"/api/v1/workspaces/{ws}"
    no_baseline = _compare(client, ws, candidate)
    assert no_baseline.status_code == 409
    assert no_baseline.json()["error"]["code"] == "baseline_not_set"
    assert store.list_comparison_records(ws) == []

    assert _pin(client, ws, baseline).status_code == 200
    same = _compare(client, ws, baseline)
    assert same.status_code == 409
    assert same.json()["error"]["code"] == "self_comparison"

    response = _compare(client, ws, candidate)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["mode"] == "CANONICAL"
    assert record["compatibility"] == {"status": "COMPARABLE", "reasons": []}
    assert record["regression_report"]["passed"] is False
    assert record["policy_version"] == "workspace-retrieval-regression-v1"
    comparison_id = record["comparison_id"]
    detail = client.get(f"{root}/comparisons/{comparison_id}", headers=HEADERS)
    listing = client.get(f"{root}/comparisons", headers=HEADERS)
    assert detail.status_code == listing.status_code == 200
    assert detail.json() == record
    assert listing.json()["comparisons"] == [record]

    failures = f"{root}/comparisons/{comparison_id}/failures"
    transition = client.get(failures, headers=HEADERS)
    assert transition.status_code == 200
    assert transition.json()["total_count"] == 1
    assert transition.json()["transitions"][0]["transition"] == "REGRESSED"
    assert transition.json()["transitions"][0]["query_id"] == "q1"
    filtered = client.get(failures + "?transition=IMPROVED", headers=HEADERS)
    assert filtered.status_code == 200
    assert filtered.json()["total_count"] == 0
    assert client.get(failures + "?query_id=q1", headers=HEADERS).json()["total_count"] == 1
    assert (
        client.get(failures + "?query_id=q&exact=false", headers=HEADERS).json()["total_count"] == 1
    )
    assert (
        client.get(failures + "?category=RETRIEVAL_MISS", headers=HEADERS).json()["total_count"]
        == 1
    )
    assert client.get(failures + "?transition=EXECUTE_CODE", headers=HEADERS).status_code == 422
    assert client.get(failures + "?query_id=", headers=HEADERS).status_code == 422
    assert "relevant_document_ids" not in transition.text
    assert "retrieved_document_ids" not in transition.text


def test_mismatch_blocks_canonical_and_exploratory_is_permanent(ctx) -> None:
    client, store, ws = ctx
    baseline = _create_run(client, ws, top_k=1)
    candidate = _create_run(client, ws, top_k=2)
    _pin(client, ws, baseline)
    blocked = _compare(client, ws, candidate)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "non_comparable"
    assert "top_k" in [r["field"] for r in blocked.json()["compatibility"]["reasons"]]
    assert store.list_comparison_records(ws) == []

    exploratory = _compare(client, ws, candidate, "EXPLORATORY_ONLY")
    assert exploratory.status_code == 201, exploratory.text
    assert exploratory.json()["mode"] == "EXPLORATORY_ONLY"
    assert exploratory.json()["compatibility"]["status"] == "NON_COMPARABLE"
    count = len(store.list_comparison_records(ws))
    impossible = client.post(
        f"/api/v1/workspaces/{ws}/comparisons",
        headers=HEADERS,
        json={"candidate_run_id": candidate, "mode": "CANONICAL", "policy_version": "loose"},
    )
    assert impossible.status_code == 422
    assert len(store.list_comparison_records(ws)) == count
    assert store.get_comparison_record(ws, exploratory.json()["comparison_id"]).mode.value == (
        "EXPLORATORY_ONLY"
    )


def test_changed_query_population_never_invents_private_transitions(ctx) -> None:
    client, _, ws = ctx
    baseline = _create_run(client, ws)
    candidate = _create_run(client, ws, ground_truth=GT_OTHER, predictions=GOOD)
    _pin(client, ws, baseline)
    created = _compare(client, ws, candidate, "EXPLORATORY_ONLY")
    assert created.status_code == 201, created.text
    failure_path = f"/api/v1/workspaces/{ws}/comparisons/{created.json()['comparison_id']}/failures"
    unavailable = client.get(failure_path, headers=HEADERS)
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "failure_evidence_unavailable"


def test_session_origin_ownership_and_untrusted_inputs_fail_closed(ctx) -> None:
    client, store, ws = ctx
    root = f"/api/v1/workspaces/{ws}"
    unauthenticated = TestClient(client.app)
    for endpoint in (f"{root}/baseline", f"{root}/comparisons"):
        assert unauthenticated.get(endpoint, headers=HEADERS).status_code == 401

    wrong_origin = client.put(
        f"{root}/baseline",
        headers={**HEADERS, "Origin": "https://evil.example"},
        json={"run_id": "run-" + "f" * 32},
    )
    assert wrong_origin.status_code == 403
    malicious = client.get(
        f"{root}/comparisons/comparison-{'f' * 32}", headers={"Host": "evil.example"}
    )
    assert malicious.status_code == 400

    first = _create_run(client, ws)
    second = _create_run(client, ws, predictions=BAD)
    _pin(client, ws, first)
    own_comparison = _compare(client, ws, second).json()["comparison_id"]
    foreign = client.post(
        "/api/v1/workspaces", headers=HEADERS, json={"display_name": "Another"}
    ).json()["workspace_id"]
    assert (
        client.get(
            f"/api/v1/workspaces/{foreign}/comparisons/{own_comparison}", headers=HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws}/comparisons/comparison-{'f' * 32}", headers=HEADERS
        ).status_code
        == 404
    )
    assert str(store.root) not in json.dumps(
        client.get(f"{root}/comparisons", headers=HEADERS).json()
    )
