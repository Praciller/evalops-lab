from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from evalops.workspace.api.app import create_workspace_app
from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
from evalops.workspace.storage import WorkspaceStore


def _client(tmp_path: Path) -> tuple[TestClient, BootstrapSessionManager, WorkspaceOrigin]:
    origin = WorkspaceOrigin(host="127.0.0.1", port=8123)
    manager = BootstrapSessionManager(bootstrap_nonce="test-bootstrap")
    app = create_workspace_app(
        WorkspaceStore(tmp_path / "root"),
        manager,
        origin,
        static_dir=tmp_path / "static",
    )
    return TestClient(app), manager, origin


def _headers(origin: WorkspaceOrigin) -> dict[str, str]:
    return {"Host": f"{origin.host}:{origin.port}", "Origin": origin.http_origin}


def test_bootstrap_sets_strict_session_cookie_and_rejects_replay(tmp_path: Path) -> None:
    client, _, origin = _client(tmp_path)
    headers = _headers(origin)

    response = client.post(
        "/api/v1/session/bootstrap", json={"nonce": "test-bootstrap"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie

    replay = client.post(
        "/api/v1/session/bootstrap", json={"nonce": "test-bootstrap"}, headers=headers
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_bootstrap"


def test_api_requires_session_and_mutations_require_exact_origin(tmp_path: Path) -> None:
    client, _, origin = _client(tmp_path)
    headers = _headers(origin)

    unauthenticated = client.get("/api/v1/workspaces", headers=headers)
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthenticated"

    client.post("/api/v1/session/bootstrap", json={"nonce": "test-bootstrap"}, headers=headers)
    wrong_origin = client.post(
        "/api/v1/workspaces",
        json={"display_name": "Blocked"},
        headers={**headers, "Origin": "http://localhost:8123"},
    )
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["error"]["code"] == "invalid_origin"

    created = client.post(
        "/api/v1/workspaces", json={"display_name": "Thai Retrieval"}, headers=headers
    )
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["display_name"] == "Thai Retrieval"
    assert workspace["workspace_id"].startswith("ws-")


def test_workspace_list_get_and_rename_are_identity_preserving(tmp_path: Path) -> None:
    client, _, origin = _client(tmp_path)
    headers = _headers(origin)
    client.post("/api/v1/session/bootstrap", json={"nonce": "test-bootstrap"}, headers=headers)
    created = client.post(
        "/api/v1/workspaces", json={"display_name": "Original"}, headers=headers
    ).json()

    listed = client.get("/api/v1/workspaces", headers=headers)
    fetched = client.get(f"/api/v1/workspaces/{created['workspace_id']}", headers=headers)
    renamed = client.patch(
        f"/api/v1/workspaces/{created['workspace_id']}",
        json={"display_name": "Renamed"},
        headers=headers,
    )

    assert listed.status_code == 200
    assert listed.json()["workspaces"][0]["workspace_id"] == created["workspace_id"]
    assert fetched.json()["workspace_id"] == created["workspace_id"]
    assert renamed.json()["workspace_id"] == created["workspace_id"]
    assert renamed.json()["display_name"] == "Renamed"


def test_safe_errors_headers_and_health_do_not_disclose_private_state(tmp_path: Path) -> None:
    client, manager, origin = _client(tmp_path)
    headers = _headers(origin)
    client.post("/api/v1/session/bootstrap", json={"nonce": "test-bootstrap"}, headers=headers)

    response = client.get("/api/v1/workspaces/ws-missing", headers=headers)
    health = client.get("/api/v1/health", headers=headers)

    assert response.status_code == 404
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message", "field", "retryable"}
    assert "Traceback" not in response.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert str(tmp_path) not in health.text
    assert manager.bootstrap_nonce not in health.text
    assert "content-security-policy" in {key.lower() for key in health.headers}
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["x-content-type-options"] == "nosniff"


def test_host_validation_applies_to_api_and_api_does_not_fall_through_to_spa(
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>workspace</html>", encoding="utf-8")
    client, _, origin = _client(tmp_path)

    wrong_host = client.get("/api/v1/health", headers={"Host": "localhost:8123"})
    unknown_api = client.get("/api/v1/not-a-route", headers=_headers(origin))
    spa = client.get("/", headers={"Host": "127.0.0.1:8123"})

    assert wrong_host.status_code == 400
    assert unknown_api.status_code == 404
    assert unknown_api.headers["content-type"].startswith("application/json")
    assert spa.status_code == 200
    assert "workspace" in spa.text


def test_openapi_schema_matches_committed_file(tmp_path: Path) -> None:
    """Ensure the committed openapi.json stays in sync with the FastAPI app."""
    import json
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[2]
    committed_path = repo_root / "apps" / "workspace" / "openapi.json"
    assert committed_path.is_file(), "apps/workspace/openapi.json must be committed"

    # Build the same schema the export script produces
    import tempfile

    from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
    from evalops.workspace.storage import WorkspaceStore

    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(_Path(tmp) / "root")
        manager = BootstrapSessionManager(bootstrap_nonce="schema-export")
        origin = WorkspaceOrigin(host="127.0.0.1", port=8000)
        from evalops.workspace.api.app import create_workspace_app

        app = create_workspace_app(store, manager, origin)
        app.openapi_url = "/openapi.json"
        schema = app.openapi()

    generated = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    committed = committed_path.read_text(encoding="utf-8")
    assert generated == committed, (
        "apps/workspace/openapi.json is out of sync with the FastAPI app. "
        "Run: python scripts/export_workspace_openapi.py"
    )
