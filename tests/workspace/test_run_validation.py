"""Phase 6.2 Task 3: constrained retrieval pairing and immutable run snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evalops.workspace.application.runs import (
    CreateRetrievalRun,
    IncompatibleInputsError,
    create_retrieval_run,
    validate_retrieval_pair,
)
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import (
    register_imported_jsonl,
    register_referenced_jsonl,
)
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

GT = (
    b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
    b'{"query_id":"q2","relevant_document_ids":["d2"]}\n'
)
PRED = (
    b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
    b'{"query_id":"q3","retrieved_document_ids":["noise"]}\n'
)


@pytest.fixture
def registered(tmp_path: Path) -> tuple[WorkspaceStore, str, str, str, Path]:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("Local retrieval").workspace_id
    truth = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="truth.jsonl",
    ).manifest
    pred = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=PRED,
        source_filename="predictions.jsonl",
    ).manifest
    return store, ws, truth.input_id, pred.input_id, root


def _request(truth: str, pred: str, **updates: object) -> CreateRetrievalRun:
    values: dict[str, object] = {
        "run_name": " Retrieval Smoke ",
        "ground_truth_input_id": truth,
        "predictions_input_id": pred,
        "top_k": 2,
        "system_name": "bm25-local",
        "dataset_name": "internal-eval-fixture",
        "dataset_version": "v1",
    }
    values.update(updates)
    return CreateRetrievalRun.model_validate(values)


def test_pair_overlap_missing_and_extra_predictions_are_warnings(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, _ = registered
    report = validate_retrieval_pair(store, ws, truth, pred)
    assert report.ground_truth_records == 2
    assert report.prediction_records == 2
    assert report.matching_query_count == 1
    assert report.missing_prediction_query_ids == ["q2"]
    assert report.extra_prediction_query_ids == ["q3"]
    assert report.blocking_issues == []
    assert {warning.code for warning in report.warnings} == {
        "MISSING_PREDICTIONS",
        "EXTRA_PREDICTIONS",
    }


def test_wrong_input_kinds_and_cross_workspace_ids_block(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, _ = registered
    swapped = validate_retrieval_pair(store, ws, pred, truth)
    assert len(swapped.blocking_issues) == 2
    assert [issue.code for issue in swapped.blocking_issues] == [
        "WRONG_INPUT_KIND",
        "WRONG_INPUT_KIND",
    ]
    other = store.create_workspace("Other").workspace_id
    cross_workspace = validate_retrieval_pair(store, other, truth, pred)
    assert len(cross_workspace.blocking_issues) == 2
    assert all(issue.code == "INVALID_INPUT" for issue in cross_workspace.blocking_issues)
    invalid = validate_retrieval_pair(store, ws, "../malicious", pred)
    assert len(invalid.blocking_issues) == 1
    assert invalid.blocking_issues[0].code == "INVALID_INPUT"


def test_run_snapshot_pins_hashes_and_authoritative_evaluator_version(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    request = _request(truth, pred)
    snapshot = create_retrieval_run(store, ws, request, git_commit="a" * 40)
    assert snapshot.run_id.startswith("run-")
    assert snapshot.workspace_id == ws
    assert snapshot.run_name == "Retrieval Smoke"
    assert snapshot.config.run_id == snapshot.run_id
    assert snapshot.config.evaluator_versions == {"retrieval": "deterministic-v1"}
    assert snapshot.config.top_k == 2
    assert snapshot.config.git_commit == "a" * 40
    assert snapshot.ground_truth_content_sha256 == hashlib.sha256(GT).hexdigest()
    assert snapshot.predictions_content_sha256 == hashlib.sha256(PRED).hexdigest()
    path = root / "workspaces" / ws / "runs" / snapshot.run_id / "config.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "workspace-run-v1"
    assert payload["run_id"] == snapshot.run_id
    assert WorkspaceStore(root).get_run_snapshot(ws, snapshot.run_id) == snapshot
    assert not list(root.rglob("*.tmp"))


def test_snapshot_is_never_mutated_in_place(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    snapshot = create_retrieval_run(store, ws, _request(truth, pred))
    path = root / "workspaces" / ws / "runs" / snapshot.run_id / "config.json"
    content = path.read_bytes()
    with pytest.raises(WorkspaceStorageError, match="already exists"):
        store.save_run_snapshot(ws, snapshot)
    assert path.read_bytes() == content
    with pytest.raises(WorkspaceStorageError):
        store.get_run_snapshot(ws, "../unsafe")
    other = store.create_workspace("Other").workspace_id
    with pytest.raises(WorkspaceStorageError):
        store.get_run_snapshot(other, snapshot.run_id)
    with pytest.raises(WorkspaceStorageError, match="ownership"):
        store.save_run_snapshot(other, snapshot)
    assert path.read_bytes() == content


def test_run_creation_rejects_wrong_kinds_and_unknown_inputs(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    with pytest.raises(IncompatibleInputsError) as caught:
        create_retrieval_run(store, ws, _request(pred, truth))
    assert [issue.code for issue in caught.value.issues] == ["WRONG_INPUT_KIND", "WRONG_INPUT_KIND"]
    with pytest.raises(IncompatibleInputsError):
        create_retrieval_run(store, ws, _request("input-" + "f" * 32, pred))
    assert list((root / "workspaces" / ws).rglob("config.json")) == []


@pytest.mark.parametrize(
    "updates",
    [
        {"top_k": 0},
        {"top_k": -1},
        {"run_name": " "},
        {"system_name": " "},
        {"dataset_name": " "},
        {"dataset_version": " "},
    ],
)
def test_run_request_rejects_invalid_fields(
    registered: tuple[WorkspaceStore, str, str, str, Path], updates: dict[str, object]
) -> None:
    _, _, truth, pred, _ = registered
    with pytest.raises(ValidationError):
        _request(truth, pred, **updates)


def test_referenced_input_mutation_before_run_creation_is_blocking(
    registered: tuple[WorkspaceStore, str, str, str, Path],
    tmp_path: Path,
) -> None:
    store, ws, truth, _, root = registered
    source = tmp_path / "referenced.jsonl"
    source.write_bytes(PRED)
    pred = register_referenced_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_PREDICTIONS, source=source
    ).manifest
    source.write_bytes(PRED + b'{"query_id":"q4","retrieved_document_ids":[]}\n')
    report = validate_retrieval_pair(store, ws, truth, pred.input_id)
    assert [issue.code for issue in report.blocking_issues] == ["INVALID_INPUT"]
    with pytest.raises(IncompatibleInputsError):
        create_retrieval_run(store, ws, _request(truth, pred.input_id))
    assert list((root / "workspaces" / ws).rglob("config.json")) == []


def test_run_snapshot_retains_frozen_hash_after_external_input_change(
    registered: tuple[WorkspaceStore, str, str, str, Path], tmp_path: Path
) -> None:
    store, ws, truth, _, root = registered
    source = tmp_path / "referenced.jsonl"
    source.write_bytes(PRED)
    pred = register_referenced_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_PREDICTIONS, source=source
    ).manifest
    snapshot = create_retrieval_run(store, ws, _request(truth, pred.input_id))
    source.write_bytes(b'{"query_id":"new","retrieved_document_ids":["x"]}\n')
    reloaded = WorkspaceStore(root).get_run_snapshot(ws, snapshot.run_id)
    assert reloaded.predictions_content_sha256 == hashlib.sha256(PRED).hexdigest()
    assert reloaded == snapshot


def test_corrupted_run_config_and_schema_are_not_silently_accepted(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    snapshot = create_retrieval_run(store, ws, _request(truth, pred))
    path = root / "workspaces" / ws / "runs" / snapshot.run_id / "config.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "workspace-run-v99"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkspaceStorageError):
        store.get_run_snapshot(ws, snapshot.run_id)
    payload["schema_version"] = "workspace-run-v1"
    payload["workspace_id"] = "ws-" + "0" * 32
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WorkspaceStorageError, match="ownership"):
        store.get_run_snapshot(ws, snapshot.run_id)


def test_failed_atomic_run_config_write_leaves_no_partial_file(
    registered: tuple[WorkspaceStore, str, str, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evalops.workspace import storage

    store, ws, truth, pred, root = registered

    def fail_link(_: object, __: object) -> None:
        raise OSError("simulated atomic creation failure")

    monkeypatch.setattr(storage.os, "link", fail_link)
    with pytest.raises(OSError, match="simulated atomic creation failure"):
        create_retrieval_run(store, ws, _request(truth, pred))
    assert list((root / "workspaces" / ws).rglob("config.json")) == []
    assert list(root.rglob("*.tmp")) == []


def test_symlinked_run_directory_does_not_escape_workspace(
    registered: tuple[WorkspaceStore, str, str, str, Path],
    tmp_path: Path,
) -> None:
    store, ws, truth, pred, root = registered
    outside = tmp_path / "outside-runs"
    outside.mkdir()
    workspace_root = root / "workspaces" / ws
    link = workspace_root / "runs"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privileges unavailable on this machine")
    with pytest.raises(WorkspaceStorageError, match="unsafe"):
        create_retrieval_run(store, ws, _request(truth, pred))
    assert list(outside.iterdir()) == []


def test_rerunning_same_config_creates_new_immutable_identity(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    first = create_retrieval_run(store, ws, _request(truth, pred))
    second = create_retrieval_run(store, ws, _request(truth, pred))
    assert first.run_id != second.run_id
    assert WorkspaceStore(root).get_run_snapshot(ws, first.run_id) == first
    assert WorkspaceStore(root).get_run_snapshot(ws, second.run_id) == second


def test_store_rejects_a_snapshot_with_forged_content_digest(
    registered: tuple[WorkspaceStore, str, str, str, Path],
) -> None:
    store, ws, truth, pred, root = registered
    snapshot = create_retrieval_run(store, ws, _request(truth, pred))
    new_id = "run-" + "f" * 32
    forged = snapshot.model_copy(
        update={
            "run_id": new_id,
            "config": snapshot.config.model_copy(update={"run_id": new_id}),
            "predictions_content_sha256": "0" * 64,
        }
    )
    with pytest.raises(WorkspaceStorageError, match="integrity mismatch"):
        store.save_run_snapshot(ws, forged)
    assert list((root / "workspaces" / ws / "runs" / forged.run_id).rglob("config.json")) == []
