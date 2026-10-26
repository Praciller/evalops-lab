"""Contract tests for Phase 6.2 Task 1 private retrieval input registration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evalops.datasets.io import load_retrieval_ground_truth, load_retrieval_predictions
from evalops.workspace.ingestion.models import (
    MAX_INPUT_BYTES,
    InputKind,
    InputSourceMode,
    InputValidationError,
)
from evalops.workspace.ingestion.service import register_imported_jsonl, register_referenced_jsonl
from evalops.workspace.storage import (
    InputHashChangedError,
    UnknownInputError,
    UnknownWorkspaceError,
    WorkspaceStorageError,
    WorkspaceStore,
)

GT = (
    b'{"query_id":"q1","relevant_document_ids":["doc1"]}\n'
    b'{"query_id":"q2","relevant_document_ids":[]}\n'
)
PRED = b'{"query_id":"q1","retrieved_document_ids":["doc1","doc2"]}\n'


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[WorkspaceStore, str, Path]:
    root = tmp_path / "workspace-root"
    store = WorkspaceStore(root)
    store.initialize()
    record = store.create_workspace("Test retrieval workspace")
    return store, record.workspace_id, root


def test_imports_ground_truth_bytes_with_immutable_hash_and_loader_compatibility(
    workspace: tuple[WorkspaceStore, str, Path],
) -> None:
    store, workspace_id, root = workspace
    first = register_imported_jsonl(
        store,
        workspace_id,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="test.jsonl",
    )
    manifest = first.manifest
    stored = root / "workspaces" / workspace_id / manifest.stored_relative_path
    assert manifest.input_id.startswith("input-")
    assert manifest.source_mode == InputSourceMode.IMPORTED
    assert manifest.source_path is None
    assert manifest.record_count == first.summary.record_count == 2
    assert manifest.content_sha256 == hashlib.sha256(GT).hexdigest()
    assert stored.read_bytes() == GT
    assert load_retrieval_ground_truth(stored) == {"q1": ["doc1"], "q2": []}
    assert WorkspaceStore(root).get_input(workspace_id, manifest.input_id) == manifest
    assert store.list_inputs(workspace_id) == [manifest]
    assert list(root.rglob("*.tmp")) == []


def test_imports_predictions_using_authoritative_loader(
    workspace: tuple[WorkspaceStore, str, Path],
) -> None:
    store, workspace_id, root = workspace
    result = register_imported_jsonl(
        store,
        workspace_id,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=PRED,
        source_filename="predictions.jsonl",
    )
    stored = root / "workspaces" / workspace_id / result.manifest.stored_relative_path
    assert result.summary.unique_query_count == 1
    assert load_retrieval_predictions(stored) == {"q1": ["doc1", "doc2"]}


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "EMPTY_INPUT"),
        (b"   \n\n", "EMPTY_INPUT"),
        (b"\xff\xfe", "INVALID_UTF8"),
        (b"{invalid json}\n", "INVALID_JSONL"),
        (b'{"query_id":123,"relevant_document_ids":["d1"]}\n', "INVALID_JSONL"),
        (
            b'{"query_id":"SENSITIVE-id","relevant_document_ids":[]}\n'
            b'{"query_id":"SENSITIVE-id","relevant_document_ids":[]}\n',
            "DUPLICATE_QUERY_ID",
        ),
    ],
)
def test_invalid_import_is_fail_closed_without_leaking_records(
    workspace: tuple[WorkspaceStore, str, Path], payload: bytes, code: str
) -> None:
    store, workspace_id, root = workspace
    with pytest.raises(InputValidationError) as caught:
        register_imported_jsonl(
            store,
            workspace_id,
            kind=InputKind.RETRIEVAL_GROUND_TRUTH,
            data=payload,
            source_filename="input.jsonl",
        )
    assert caught.value.code == code
    assert "SENSITIVE-id" not in str(caught.value)
    assert store.list_inputs(workspace_id) == []
    assert list((root / "workspaces" / workspace_id / "inputs").rglob("*.jsonl")) == []


def test_reference_resolves_file_and_does_not_copy_data(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path
) -> None:
    store, workspace_id, root = workspace
    source = tmp_path / "outside-input.jsonl"
    source.write_bytes(GT)
    result = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
    )
    assert result.manifest.source_mode == InputSourceMode.REFERENCED
    assert result.manifest.source_path == str(source.resolve())
    assert result.manifest.stored_relative_path is None
    assert result.manifest.source_sha256 == hashlib.sha256(GT).hexdigest()
    assert list((root / "workspaces" / workspace_id).rglob("*.jsonl")) == []
    assert WorkspaceStore(root).list_inputs(workspace_id) == [result.manifest]


def test_reference_resolves_symlink_to_original(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path
) -> None:
    store, workspace_id, _ = workspace
    source = tmp_path / "original.jsonl"
    source.write_bytes(PRED)
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink privileges unavailable on this machine")
    result = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_PREDICTIONS, source=link
    )
    assert result.manifest.source_path == str(source.resolve())


@pytest.mark.parametrize("source_name", ["bad.csv", "input.txt", "input"])
def test_unsupported_extension_is_rejected(
    workspace: tuple[WorkspaceStore, str, Path], source_name: str, tmp_path: Path
) -> None:
    store, workspace_id, _ = workspace
    with pytest.raises(InputValidationError, match=r"only \.jsonl"):
        register_imported_jsonl(
            store,
            workspace_id,
            kind=InputKind.RETRIEVAL_GROUND_TRUTH,
            data=GT,
            source_filename=source_name,
        )
    path = tmp_path / source_name
    path.write_bytes(GT)
    with pytest.raises(InputValidationError):
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=path
        )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "relative.jsonl",
        "../relative.jsonl",
        "//server/share/input.jsonl",
        r"\\server\share\input.jsonl",
    ],
)
def test_reference_requires_absolute_local_path(
    workspace: tuple[WorkspaceStore, str, Path], unsafe_path: str
) -> None:
    store, workspace_id, root = workspace
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store,
            workspace_id,
            kind=InputKind.RETRIEVAL_GROUND_TRUTH,
            source=Path(unsafe_path),
        )
    assert caught.value.code == "INVALID_REFERENCE_PATH"
    assert store.list_inputs(workspace_id) == []
    assert not list((root / "workspaces" / workspace_id).rglob("*.jsonl"))


def test_reference_rejects_network_target_after_resolve(
    workspace: tuple[WorkspaceStore, str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, workspace_id, _ = workspace
    source = tmp_path / "local-input.jsonl"
    source.write_bytes(GT)
    original_resolve = Path.resolve

    def redirected(path: Path, *args: object, **kwargs: object) -> Path:
        if path == source:
            return Path(r"\\server\share\remote.jsonl")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
        )
    assert caught.value.code == "INVALID_REFERENCE_PATH"


def test_reference_non_file_and_missing_file_are_rejected(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path
) -> None:
    store, workspace_id, _ = workspace
    folder = tmp_path / "directory.jsonl"
    folder.mkdir()
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=folder
        )
    assert caught.value.code == "NOT_A_FILE"
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store,
            workspace_id,
            kind=InputKind.RETRIEVAL_GROUND_TRUTH,
            source=tmp_path / "absent.jsonl",
        )
    assert caught.value.code == "UNREADABLE_INPUT"


def test_unreadable_reference_is_a_safe_error(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, workspace_id, _ = workspace
    source = tmp_path / "read-error.jsonl"
    source.write_bytes(GT)
    original_open = Path.open

    def deny(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path == source and mode == "rb":
            raise PermissionError("SENSITIVE local path")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
        )
    assert caught.value.code == "UNREADABLE_INPUT"
    assert "SENSITIVE" not in str(caught.value)


def test_invalid_ids_and_cross_workspace_ownership_fail_closed(
    workspace: tuple[WorkspaceStore, str, Path],
) -> None:
    store, workspace_id, _ = workspace
    result = register_imported_jsonl(
        store,
        workspace_id,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="input.jsonl",
    )
    with pytest.raises(UnknownInputError):
        store.get_input(workspace_id, "../outside")
    other = store.create_workspace("Other workspace")
    with pytest.raises(UnknownInputError):
        store.get_input(other.workspace_id, result.manifest.input_id)
    with pytest.raises(UnknownWorkspaceError):
        store.list_inputs("ws-unknown")


def test_manifest_is_immutable_and_failure_cleans_imported_bytes(
    workspace: tuple[WorkspaceStore, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, workspace_id, root = workspace
    first = register_imported_jsonl(
        store,
        workspace_id,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GT,
        source_filename="first.jsonl",
    )
    with pytest.raises(WorkspaceStorageError, match="already registered"):
        store.save_input_manifest(workspace_id, first.manifest)
    assert store.get_input(workspace_id, first.manifest.input_id) == first.manifest

    def fail_manifest(_: str, __: object) -> None:
        raise OSError("injected failure")

    monkeypatch.setattr(store, "save_input_manifest", fail_manifest)
    with pytest.raises(OSError, match="injected failure"):
        register_imported_jsonl(
            store,
            workspace_id,
            kind=InputKind.RETRIEVAL_GROUND_TRUTH,
            data=GT,
            source_filename="second.jsonl",
        )
    imported = root / "workspaces" / workspace_id / "inputs" / "imported"
    assert len(list(imported.glob("*.jsonl"))) == 1
    assert not list(root.rglob("*.tmp"))


def test_referenced_manifest_rejects_network_path_after_registration(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path
) -> None:
    store, workspace_id, root = workspace
    source = tmp_path / "safe-input.jsonl"
    source.write_bytes(GT)
    registered = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
    )
    manifest_path = (
        root
        / "workspaces"
        / workspace_id
        / "inputs"
        / "manifests"
        / f"{registered.manifest.input_id}.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_path"] = r"\\server\share\remote.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(WorkspaceStorageError, match="source path is unsafe"):
        store.read_input_bytes(workspace_id, registered.manifest.input_id)


def test_referenced_input_rejects_network_redirect_at_read_time(
    workspace: tuple[WorkspaceStore, str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, workspace_id, _ = workspace
    source = tmp_path / "safe-input.jsonl"
    source.write_bytes(GT)
    registered = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
    )
    original_resolve = Path.resolve

    def redirected(path: Path, *args: object, **kwargs: object) -> Path:
        if path == source:
            return Path(r"\\server\share\remote.jsonl")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    with pytest.raises(WorkspaceStorageError, match="source path is unsafe"):
        store.read_input_bytes(workspace_id, registered.manifest.input_id)


def test_referenced_file_size_is_bounded_on_registration_and_runtime(
    workspace: tuple[WorkspaceStore, str, Path], tmp_path: Path
) -> None:
    store, workspace_id, _ = workspace
    source = tmp_path / "too-large-after-import.jsonl"
    source.write_bytes(GT)
    first = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
    )
    assert store.read_input_bytes(workspace_id, first.manifest.input_id) == GT
    # Sparse extension avoids allocating a large fixture in the test process.
    with source.open("r+b") as handle:
        handle.truncate(MAX_INPUT_BYTES + 1)

    with pytest.raises(InputHashChangedError, match="10 MiB"):
        store.read_input_bytes(workspace_id, first.manifest.input_id)

    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
        )
    assert caught.value.code == "INPUT_TOO_LARGE"
    assert "too-large-after-import" not in str(caught.value)
    assert len(store.list_inputs(workspace_id)) == 1


def test_reference_read_cap_survives_file_growth_after_stat(
    workspace: tuple[WorkspaceStore, str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    store, workspace_id, _ = workspace
    source = tmp_path / "grow-after-stat.jsonl"
    source.write_bytes(GT)
    registered = register_referenced_jsonl(
        store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
    )
    original_open = Path.open
    read_sizes: list[int] = []

    class GrowingReader(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            assert size == MAX_INPUT_BYTES + 1, "file read must be bounded"
            return super().read(size)

    def changed_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path == source and mode == "rb":
            return GrowingReader(b"x" * (MAX_INPUT_BYTES + 1))
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", changed_open)
    with pytest.raises(InputHashChangedError, match="10 MiB"):
        store.read_input_bytes(workspace_id, registered.manifest.input_id)
    with pytest.raises(InputValidationError) as caught:
        register_referenced_jsonl(
            store, workspace_id, kind=InputKind.RETRIEVAL_GROUND_TRUTH, source=source
        )
    assert caught.value.code == "INPUT_TOO_LARGE"
    assert read_sizes == [MAX_INPUT_BYTES + 1, MAX_INPUT_BYTES + 1]
