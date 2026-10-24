"""Phase 6.4 Task 3: second explicit confirmation, non-overwrite and failure cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import evalops.workspace.application.exports as module
from evalops.export.models import VerificationStatus
from evalops.workspace.application.comparisons import ComparisonService
from evalops.workspace.application.exports import ExportService
from evalops.workspace.application.runs import CreateRetrievalRun, RetrievalRunService
from evalops.workspace.comparison.models import ComparisonMode
from evalops.workspace.export.models import (
    ConfirmExportRequest,
    ExportClassification,
    ExportManifest,
    WorkspaceExportDataKind,
)
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.jobs.models import JobState
from evalops.workspace.storage import WorkspaceStore

TRUTH = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
GOOD = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
BAD = b'{"query_id":"q1","retrieved_document_ids":["d2"]}\n'
NOW = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.fixture
def ctx(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "private")
    store.initialize()
    ws = store.create_workspace("confirmation test").workspace_id
    runner = RetrievalRunService(store)
    runner.start()
    dest = tmp_path / "selected-output"
    dest.mkdir()
    try:
        yield store, ws, runner, dest, tmp_path
    finally:
        runner.stop()


def _run(store: WorkspaceStore, ws: str, runner: RetrievalRunService, predictions: bytes) -> str:
    gt = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=TRUTH, source_filename="truth.jsonl",
    ).manifest.input_id
    pred = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=predictions, source_filename="pred.jsonl",
    ).manifest.input_id
    job = runner.create_and_enqueue(
        ws,
        CreateRetrievalRun(
            run_name="confirm-export", ground_truth_input_id=gt,
            predictions_input_id=pred, top_k=1, system_name="synthetic",
            dataset_name="dataset", dataset_version="v1",
        ),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = store.get_job_record(ws, job.job_id).state
        if state == JobState.COMPLETE:
            return job.run_id
        if state in {JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED}:
            pytest.fail(f"run failed: {state}")
        time.sleep(0.01)
    pytest.fail("timed out")


def _classification() -> ExportClassification:
    return ExportClassification(
        verification_status=VerificationStatus.UNVERIFIED,
        data_kind=WorkspaceExportDataKind.SYNTHETIC_FIXTURE,
        limitations=["Synthetic local run only"],
    )


def _request(preview_id: str, path: Path) -> ConfirmExportRequest:
    return ConfirmExportRequest(preview_id=preview_id, destination_directory=str(path))


def _manifest_path(tmp_path: Path, ws: str, export_id: str) -> Path:
    return tmp_path / "private" / "workspaces" / ws / "exports" / "manifests" / f"{export_id}.json"


def test_run_confirmation_is_byte_identical_and_records_private_history(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    before = service.get_prepared_files(ws, preview.preview_id)
    assert list(dest.iterdir()) == []
    manifest = service.confirm(ws, _request(preview.preview_id, dest))
    assert isinstance(manifest, ExportManifest)
    assert manifest.source_type == "run"
    assert manifest.source_id == run_id
    assert manifest.destination == str(dest / f"workspace-{run_id}.json")
    assert len(manifest.files) == 1
    filename, data = next(iter(before.items()))
    output = dest / filename
    assert output.is_file()
    assert output.read_bytes() == data
    assert manifest.files[0].sha256 == hashlib.sha256(data).hexdigest()
    assert _manifest_path(tmp, ws, manifest.export_id).is_file()
    payload = json.loads(_manifest_path(tmp, ws, manifest.export_id).read_text("utf-8"))
    assert payload == manifest.model_dump(mode="json")
    assert not any(path.name.startswith(".evalops-") for path in dest.iterdir())
    with pytest.raises(LookupError):
        service.confirm(ws, _request(preview.preview_id, dest))


def test_comparison_confirm_commits_complete_four_file_bundle(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    base = _run(store, ws, runner, GOOD)
    candidate = _run(store, ws, runner, BAD)
    compare = ComparisonService(store)
    compare.set_baseline(ws, base)
    record = compare.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    expected = service.get_prepared_files(ws, preview.preview_id)
    assert preview.eligible
    manifest = service.confirm(ws, _request(preview.preview_id, dest))
    output = Path(manifest.destination)
    assert output.is_dir()
    assert {item.name for item in output.iterdir()} == {
        "baseline.json", "candidate.json", "comparison.json", "index.json"
    }
    assert len(manifest.files) == 4
    for name, data in expected.items():
        assert (output / name.split("/")[1]).read_bytes() == data
    assert _manifest_path(tmp, ws, manifest.export_id).is_file()
    assert list(dest.iterdir()) == [output]
    assert not any(p.name.startswith(".evalops-") for p in dest.iterdir())


def test_confirmation_requires_absolute_existing_directory_and_valid_request(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    for invalid in ["relative/output", str(tmp / "missing"), str(tmp / "file.txt"), ""]:
        if invalid == str(tmp / "file.txt"):
            (tmp / "file.txt").write_text("unchanged")
        if not invalid:
            with pytest.raises(ValidationError):
                ConfirmExportRequest(preview_id=preview.preview_id, destination_directory="")
        else:
            with pytest.raises(ValueError):
                service.confirm(
                    ws, ConfirmExportRequest(
                        preview_id=preview.preview_id, destination_directory=invalid
                    )
                )
    assert list(dest.iterdir()) == []
    assert not (tmp / "private" / "workspaces" / ws / "exports").exists()
    with pytest.raises(ValidationError):
        ConfirmExportRequest.model_validate({
            "preview_id": preview.preview_id,
            "destination_directory": str(dest),
            "publish_to_github": True,
        })


def test_existing_run_destination_never_overwritten(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    target = dest / f"workspace-{run_id}.json"
    target.write_bytes(b"OWNER_EXISTING_FILE")
    with pytest.raises(ValueError, match="already exists"):
        service.confirm(ws, _request(preview.preview_id, dest))
    assert target.read_bytes() == b"OWNER_EXISTING_FILE"
    assert not (tmp / "private" / "workspaces" / ws / "exports").exists()


def test_existing_empty_comparison_folder_never_replaced(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    baseline = _run(store, ws, runner, GOOD)
    candidate = _run(store, ws, runner, BAD)
    comparison = ComparisonService(store)
    comparison.set_baseline(ws, baseline)
    record = comparison.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    target = dest / f"workspace-{record.comparison_id}"
    target.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        service.confirm(ws, _request(preview.preview_id, dest))
    assert target.is_dir() and list(target.iterdir()) == []
    assert not (tmp / "private" / "workspaces" / ws / "exports").exists()


def test_expired_unknown_or_other_workspace_preview_refused(ctx) -> None:
    store, ws, runner, dest, _ = ctx
    run_id = _run(store, ws, runner, GOOD)
    clock = [NOW]
    service = ExportService(store, clock=lambda: clock[0])
    preview = service.preview_run(ws, run_id, _classification())
    with pytest.raises(LookupError):
        service.confirm("ws-" + "f" * 32, _request(preview.preview_id, dest))
    with pytest.raises(LookupError):
        service.confirm(ws, _request("preview-" + "f" * 32, dest))
    clock[0] += timedelta(minutes=15)
    with pytest.raises(LookupError):
        service.confirm(ws, _request(preview.preview_id, dest))
    assert list(dest.iterdir()) == []


def test_source_changed_after_run_preview_refuses_write(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    result = tmp / "private" / "workspaces" / ws / "runs" / run_id / "result.json"
    result.write_bytes(result.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source changed"):
        service.confirm(ws, _request(preview.preview_id, dest))
    assert list(dest.iterdir()) == []


def test_source_changed_after_comparison_preview_refuses_write(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    base = _run(store, ws, runner, GOOD)
    candidate = _run(store, ws, runner, BAD)
    service_comparison = ComparisonService(store)
    service_comparison.set_baseline(ws, base)
    record = service_comparison.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    source = (tmp / "private" / "workspaces" / ws / "comparisons" /
              record.comparison_id / "result.json")
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source changed"):
        service.confirm(ws, _request(preview.preview_id, dest))
    assert list(dest.iterdir()) == []


def test_run_stage_failure_removes_only_own_temporary_file(
    ctx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, runner, dest, tmp = ctx
    run_id = _run(store, ws, runner, GOOD)
    preview_service = ExportService(store, clock=lambda: NOW)
    preview = preview_service.preview_run(ws, run_id, _classification())
    def failed_link(source: object, destination: object):
        raise OSError("simulated hard-link failure")
    monkeypatch.setattr(module.os, "link", failed_link)
    with pytest.raises(OSError, match="simulated"):
        preview_service.confirm(ws, _request(preview.preview_id, dest))
    assert list(dest.iterdir()) == []
    assert not (tmp / "private" / "workspaces" / ws / "exports").exists()


def test_bundle_stage_failure_removes_only_own_temporary_dir(
    ctx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, runner, dest, tmp = ctx
    base = _run(store, ws, runner, GOOD)
    candidate = _run(store, ws, runner, BAD)
    cmp_service = ComparisonService(store)
    cmp_service.set_baseline(ws, base)
    record = cmp_service.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    preview_service = ExportService(store, clock=lambda: NOW)
    preview = preview_service.preview_comparison(ws, record.comparison_id, _classification())
    sentinel = dest / "owner.txt"
    sentinel.write_bytes(b"DO_NOT_DELETE")
    def failed_rename(source: Path, destination: Path):
        raise OSError("simulated atomic rename failure")
    monkeypatch.setattr(module, "_exclusive_directory_commit", failed_rename)
    with pytest.raises(OSError, match="simulated"):
        preview_service.confirm(ws, _request(preview.preview_id, dest))
    assert list(dest.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"DO_NOT_DELETE"
    assert not (tmp / "private" / "workspaces" / ws / "exports").exists()


def test_exclusive_folder_rename_does_not_clobber_existing_empty_dir(tmp_path: Path) -> None:
    source = tmp_path / "staged"
    target = tmp_path / "owned"
    source.mkdir()
    (source / "test.json").write_text("staged")
    target.mkdir()
    with pytest.raises(OSError):
        module._exclusive_directory_commit(source, target)
    assert source.is_dir() and (source / "test.json").is_file()
    assert target.is_dir() and list(target.iterdir()) == []


def test_confirmation_does_not_delete_completed_output_on_private_manifest_fault(
    ctx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, runner, dest, _ = ctx
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    def failed_manifest(*args: object, **kwargs: object):
        raise OSError("private disk failure")
    monkeypatch.setattr(store, "save_export_manifest", failed_manifest)
    with pytest.raises(OSError, match="private disk failure"):
        service.confirm(ws, _request(preview.preview_id, dest))
    # The owner's output has been written; never roll it back or overwrite it.
    assert (dest / f"workspace-{run_id}.json").is_file()


def test_symlink_destination_rejected(ctx) -> None:
    store, ws, runner, dest, tmp = ctx
    link = tmp / "target-alias"
    try:
        link.symlink_to(dest, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    run_id = _run(store, ws, runner, GOOD)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_run(ws, run_id, _classification())
    with pytest.raises(ValueError, match="non-symlink"):
        service.confirm(ws, _request(preview.preview_id, link))
    assert list(dest.iterdir()) == []
