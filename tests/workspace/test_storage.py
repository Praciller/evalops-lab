from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.workspace import storage
from evalops.workspace.models import WORKSPACE_REGISTRY_SCHEMA_VERSION, WORKSPACE_SCHEMA_VERSION
from evalops.workspace.storage import (
    DuplicateWorkspaceError,
    UnknownWorkspaceError,
    UnsupportedSchemaVersionError,
    WorkspaceStore,
)


def test_initialize_creates_empty_versioned_registry(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace-root")

    store.initialize()

    registry = json.loads((tmp_path / "workspace-root" / "registry.json").read_text())
    assert registry == {
        "schema_version": WORKSPACE_REGISTRY_SCHEMA_VERSION,
        "workspace_ids": [],
    }
    assert store.list_workspaces() == []


def test_workspace_identity_survives_create_list_get_rename_and_restart(tmp_path: Path) -> None:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()

    created = store.create_workspace("Thai Retrieval")
    renamed = store.rename_workspace(created.workspace_id, "Renamed Workspace")
    restarted = WorkspaceStore(root)

    assert created.workspace_id.startswith("ws-")
    assert renamed.workspace_id == created.workspace_id
    assert renamed.display_name == "Renamed Workspace"
    assert restarted.get_workspace(created.workspace_id) == renamed
    assert restarted.list_workspaces() == [renamed]


def test_store_rejects_duplicate_and_unknown_workspace_ids(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace-root")
    store.initialize()
    first = store.create_workspace("First")

    registry_path = tmp_path / "workspace-root" / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": WORKSPACE_REGISTRY_SCHEMA_VERSION,
                "workspace_ids": [first.workspace_id, first.workspace_id],
            }
        )
    )
    with pytest.raises(DuplicateWorkspaceError):
        store.list_workspaces()

    registry_path.write_text(
        json.dumps(
            {
                "schema_version": WORKSPACE_REGISTRY_SCHEMA_VERSION,
                "workspace_ids": ["ws-does-not-exist"],
            }
        )
    )
    with pytest.raises(UnknownWorkspaceError):
        store.list_workspaces()
    with pytest.raises(UnknownWorkspaceError):
        store.get_workspace("ws-does-not-exist")


def test_store_rejects_unknown_schema_versions(tmp_path: Path) -> None:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()
    registry_path = root / "registry.json"
    registry_path.write_text(
        json.dumps({"schema_version": "workspace-registry-v999", "workspace_ids": []})
    )

    with pytest.raises(UnsupportedSchemaVersionError):
        store.list_workspaces()


def test_failed_atomic_write_preserves_existing_canonical_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()
    original = (root / "registry.json").read_text()

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError):
        store.create_workspace("Never Persisted")

    assert (root / "registry.json").read_text() == original
    assert json.loads((root / "registry.json").read_text())["workspace_ids"] == []
    assert not list(root.rglob("*.tmp"))


def test_workspace_json_has_version_and_stable_metadata(tmp_path: Path) -> None:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()
    record = store.create_workspace("Evidence")

    payload = json.loads((root / "workspaces" / record.workspace_id / "workspace.json").read_text())
    assert payload["schema_version"] == WORKSPACE_SCHEMA_VERSION
    assert payload["workspace_id"] == record.workspace_id
    assert payload["created_at"] == record.created_at.isoformat().replace("+00:00", "Z")
