"""Phase 6.4 Task 4 API: same-origin explicit preview and confirmation."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import evalops.workspace.application.exports as export_module
from evalops.workspace.api.app import create_workspace_app
from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
from evalops.workspace.storage import WorkspaceStore

HEADERS = {"Host": "127.0.0.1:8123", "Origin": "http://127.0.0.1:8123"}
TRUTH = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
GOOD = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
BAD = b'{"query_id":"q1","retrieved_document_ids":["d2"]}\n'


@pytest.fixture
def app_context(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "private")
    auth = BootstrapSessionManager(bootstrap_nonce="TEST_NONCE_ONLY")
    app = create_workspace_app(store, auth, WorkspaceOrigin(host="127.0.0.1", port=8123))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session/bootstrap",
            headers=HEADERS,
            json={"nonce": "TEST_NONCE_ONLY"},
        )
        assert response.status_code == 200
        created = client.post(
            "/api/v1/workspaces",
            headers=HEADERS,
            json={"display_name": "Export API test"},
        )
        assert created.status_code == 201
        ws = created.json()["workspace_id"]
        destination = tmp_path / "selected-output"
        destination.mkdir()
        yield client, store, ws, destination, tmp_path


def _run(client: TestClient, ws: str, predictions: bytes) -> str:
    inputs = []
    for kind, data in [
        ("retrieval_ground_truth", TRUTH),
        ("retrieval_predictions", predictions),
    ]:
        result = client.post(
            f"/api/v1/workspaces/{ws}/inputs/upload",
            headers=HEADERS,
            data={"kind": kind},
            files={"file": ("fixture.jsonl", data)},
        )
        assert result.status_code == 201, result.text
        inputs.append(result.json()["input_id"])
    response = client.post(
        f"/api/v1/workspaces/{ws}/runs",
        headers=HEADERS,
        json={
            "run_name": "Export API fixture",
            "ground_truth_input_id": inputs[0],
            "predictions_input_id": inputs[1],
            "top_k": 1,
            "system_name": "fixture",
            "dataset_name": "synthetic-dataset",
            "dataset_version": "v1",
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS).json()
        if job["state"] == "COMPLETE":
            return run_id
        if job["state"] in {"FAILED", "INTERRUPTED", "CANCELLED"}:
            pytest.fail(f"run failed: {job}")
        time.sleep(0.01)
    pytest.fail("job did not finish")


def _preview(client: TestClient, ws: str, source_id: str, source_type: str = "run",
             *, status: str = "UNVERIFIED", kind: str = "SYNTHETIC_FIXTURE"):
    return client.post(
        f"/api/v1/workspaces/{ws}/exports/preview",
        headers=HEADERS,
        json={
            "source_type": source_type,
            "source_id": source_id,
            "classification": {
                "verification_status": status,
                "data_kind": kind,
                "limitations": ["Synthetic fixture only"],
            },
        },
    )


def _compare(client: TestClient, ws: str, base: str, other: str, mode: str = "CANONICAL"):
    pin = client.put(
        f"/api/v1/workspaces/{ws}/baseline",
        headers=HEADERS,
        json={"run_id": base},
    )
    assert pin.status_code == 200
    record = client.post(
        f"/api/v1/workspaces/{ws}/comparisons",
        headers=HEADERS,
        json={"candidate_run_id": other, "mode": mode},
    )
    assert record.status_code == 201, record.text
    return record.json()["comparison_id"]


def test_two_step_run_api_only_writes_after_explicit_confirm(app_context) -> None:
    client, store, ws, destination, tmp = app_context
    run_id = _run(client, ws, GOOD)
    response = _preview(client, ws, run_id)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["eligible"]
    assert len(preview["output_files"]) == 1
    assert preview["classification"]["verification_status"] == "UNVERIFIED"
    assert preview["included"] and preview["removed"] and preview["transformed"]
    assert list(destination.iterdir()) == []
    before = client.get(f"/api/v1/workspaces/{ws}/exports", headers=HEADERS)
    assert before.status_code == 200 and before.json()["exports"] == []

    confirm = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": preview["preview_id"], "destination_directory": str(destination)},
    )
    assert confirm.status_code == 201, confirm.text
    manifest = confirm.json()
    assert manifest["source_type"] == "run"
    assert manifest["destination"] == str(destination / f"workspace-{run_id}.json")
    assert Path(manifest["destination"]).is_file()
    assert manifest["files"][0]["sha256"] == preview["output_files"][0]["sha256"]
    after = client.get(f"/api/v1/workspaces/{ws}/exports", headers=HEADERS)
    assert after.status_code == 200
    assert after.json()["exports"] == [manifest]
    assert not (tmp / "apps" / "web" / "public").exists()
    repeated = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": preview["preview_id"], "destination_directory": str(destination)},
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "export_preview_expired"


def test_canonical_comparison_exports_only_exact_public_bundle(app_context) -> None:
    client, _, ws, destination, _ = app_context
    baseline = _run(client, ws, GOOD)
    candidate = _run(client, ws, BAD)
    comparison_id = _compare(client, ws, baseline, candidate)
    preview = _preview(client, ws, comparison_id, "comparison")
    assert preview.status_code == 200
    detail = preview.json()
    assert detail["eligible"] and len(detail["output_files"]) == 4
    assert list(destination.iterdir()) == []
    exported = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": detail["preview_id"], "destination_directory": str(destination)},
    )
    assert exported.status_code == 201, exported.text
    folder = Path(exported.json()["destination"])
    assert folder.is_dir()
    assert {p.name for p in folder.iterdir()} == {
        "baseline.json", "candidate.json", "comparison.json", "index.json"
    }
    assert "transitions" not in (folder / "comparison.json").read_text("utf-8")


def test_exploratory_never_returns_publishable_preview(app_context) -> None:
    client, _, ws, destination, _ = app_context
    baseline = _run(client, ws, GOOD)
    candidate = _run(client, ws, BAD)
    comparison_id = _compare(client, ws, baseline, candidate, "EXPLORATORY_ONLY")
    preview = _preview(client, ws, comparison_id, "comparison")
    assert preview.status_code == 200
    assert preview.json()["eligible"] is False
    assert preview.json()["blocking_reasons"] == ["NON_CANONICAL_COMPARISON"]
    assert preview.json()["output_files"] == []
    assert list(destination.iterdir()) == []


def test_rejects_official_kind_invalid_source_type_and_extra_fields(app_context) -> None:
    client, _, ws, _, _ = app_context
    run = _run(client, ws, GOOD)
    assert _preview(client, ws, run, kind="OFFICIAL_BENCHMARK").status_code == 422
    wrong_type = _preview(client, ws, run, source_type="comparison")
    assert wrong_type.status_code == 422
    assert wrong_type.json()["error"]["code"] == "invalid_source_type"
    not_run = _preview(client, ws, run, status="NOT_RUN")
    assert not_run.status_code == 200
    assert not_run.json()["eligible"] is False
    assert not_run.json()["blocking_reasons"] == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]
    malicious = client.post(
        f"/api/v1/workspaces/{ws}/exports/preview",
        headers=HEADERS,
        json={
            "source_type": "run",
            "source_id": run,
            "classification": {
                "verification_status": "UNVERIFIED", "data_kind": "SYNTHETIC_FIXTURE",
                "claim_scope": "BENCHMARK_RESULT",
            },
        },
    )
    assert malicious.status_code == 422


def test_auth_origin_and_cross_workspace_preview_isolation(app_context) -> None:
    client, _, ws, _, _ = app_context
    run = _run(client, ws, GOOD)
    new = client.post(
        "/api/v1/workspaces", headers=HEADERS, json={"display_name": "foreign"}
    ).json()["workspace_id"]
    assert _preview(client, new, run).json()["eligible"] is False

    unauthenticated = TestClient(client.app)
    for path in [
        f"/api/v1/workspaces/{ws}/exports",
        f"/api/v1/workspaces/{ws}/exports/preview",
        f"/api/v1/workspaces/{ws}/exports/confirm",
    ]:
        if path.endswith("/exports"):
            response = unauthenticated.get(path, headers=HEADERS)
        else:
            response = unauthenticated.post(path, headers=HEADERS, json={})
        assert response.status_code == 401

    wrong_origin = client.post(
        f"/api/v1/workspaces/{ws}/exports/preview",
        headers={**HEADERS, "Origin": "https://attacker.example"},
        json={},
    )
    assert wrong_origin.status_code == 403


def test_expiry_source_drift_conflict_and_existing_target_safe_errors(
    app_context, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, ws, destination, tmp = app_context
    run = _run(client, ws, GOOD)
    response = _preview(client, ws, run)
    preview_id = response.json()["preview_id"]
    result_file = tmp / "private" / "workspaces" / ws / "runs" / run / "result.json"
    result_file.write_bytes(result_file.read_bytes() + b" ")
    changed = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": preview_id, "destination_directory": str(destination)},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "export_source_changed"
    assert str(tmp) not in changed.text
    assert list(destination.iterdir()) == []

    unknown = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={
            "preview_id": "preview-" + "e" * 32,
            "destination_directory": str(destination),
        },
    )
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "export_preview_expired"

    # Expire subsequent previews without relying on wall-clock sleeps.
    original_lifetime = export_module.PREVIEW_LIFETIME
    monkeypatch.setattr(export_module, "PREVIEW_LIFETIME", timedelta(minutes=-1))
    try:
        stale = _preview(client, ws, run)
        assert stale.json()["eligible"] is False  # tampered run is rejected
    finally:
        monkeypatch.setattr(export_module, "PREVIEW_LIFETIME", original_lifetime)


def test_explicit_directory_validation_and_destination_collision(app_context) -> None:
    client, _, ws, destination, _ = app_context
    run = _run(client, ws, GOOD)
    first = _preview(client, ws, run).json()
    invalid = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": first["preview_id"], "destination_directory": "relative/path"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "export_destination_invalid"

    target = destination / f"workspace-{run}.json"
    target.write_bytes(b"OWNER_DATA")
    collision = client.post(
        f"/api/v1/workspaces/{ws}/exports/confirm",
        headers=HEADERS,
        json={"preview_id": first["preview_id"], "destination_directory": str(destination)},
    )
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "export_destination_exists"
    assert target.read_bytes() == b"OWNER_DATA"
