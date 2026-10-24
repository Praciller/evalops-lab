"""Phase 6.4 Task 2: canonical comparison bundle preview without publication."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

import evalops.workspace.application.exports as module
from evalops.export.models import VerificationStatus
from evalops.workspace.application.comparisons import ComparisonService
from evalops.workspace.application.exports import ExportService
from evalops.workspace.application.runs import CreateRetrievalRun, RetrievalRunService
from evalops.workspace.comparison.models import ComparisonMode
from evalops.workspace.export.models import ExportClassification, WorkspaceExportDataKind
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.jobs.models import JobState
from evalops.workspace.storage import WorkspaceStore

GROUND = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
GOOD = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
BAD = b'{"query_id":"q1","retrieved_document_ids":["d2"]}\n'
NOW = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.fixture
def context(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "local-private")
    store.initialize()
    ws = store.create_workspace("comparison export fixture").workspace_id
    runner = RetrievalRunService(store)
    runner.start()
    try:
        yield store, ws, runner, tmp_path
    finally:
        runner.stop()


def _run(store: WorkspaceStore, ws: str, runner: RetrievalRunService, predictions: bytes) -> str:
    truth = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_GROUND_TRUTH,
        data=GROUND,
        source_filename="truth.jsonl",
    ).manifest.input_id
    pred = register_imported_jsonl(
        store,
        ws,
        kind=InputKind.RETRIEVAL_PREDICTIONS,
        data=predictions,
        source_filename="pred.jsonl",
    ).manifest.input_id
    job = runner.create_and_enqueue(
        ws,
        CreateRetrievalRun(
            run_name="export-fixture",
            ground_truth_input_id=truth,
            predictions_input_id=pred,
            top_k=1,
            system_name="local-retriever",
            dataset_name="synthetic-dataset",
            dataset_version="v1",
        ),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = store.get_job_record(ws, job.job_id).state
        if state == JobState.COMPLETE:
            return job.run_id
        if state in {JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED}:
            pytest.fail(f"unexpected job state: {state}")
        time.sleep(0.01)
    pytest.fail("timed out on local evaluation")


def _make_comparison(context, *, mode: ComparisonMode = ComparisonMode.CANONICAL):
    store, ws, runner, tmp = context
    baseline = _run(store, ws, runner, GOOD)
    candidate = _run(store, ws, runner, BAD)
    service = ComparisonService(store)
    service.set_baseline(ws, baseline)
    record = service.create_comparison(ws, candidate, mode=mode)
    return store, ws, record, tmp


def _classification(
    status: VerificationStatus = VerificationStatus.UNVERIFIED,
    kind: WorkspaceExportDataKind = WorkspaceExportDataKind.SYNTHETIC_FIXTURE,
) -> ExportClassification:
    return ExportClassification(
        verification_status=status,
        data_kind=kind,
        limitations=["Local synthetic fixture with no independent validation"],
    )


def test_canonical_bundle_has_four_deterministic_public_artifacts(context) -> None:
    store, ws, record, tmp = _make_comparison(context)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    assert preview.eligible
    assert preview.source_type == "comparison"
    assert preview.blocking_reasons == []
    assert len(preview.output_files) == 4
    artifact_id = f"workspace-{record.comparison_id}"
    assert [row.filename for row in preview.output_files] == [
        f"{artifact_id}/baseline.json",
        f"{artifact_id}/candidate.json",
        f"{artifact_id}/comparison.json",
        f"{artifact_id}/index.json",
    ]
    bundle = service.get_prepared_files(ws, preview.preview_id)
    assert set(bundle) == {item.filename for item in preview.output_files}
    for item in preview.output_files:
        assert item.sha256 == hashlib.sha256(bundle[item.filename]).hexdigest()
        assert item.size_bytes == len(bundle[item.filename])
        assert bundle[item.filename].endswith(b"\n")
        assert str(tmp).encode() not in bundle[item.filename]

    baseline = json.loads(bundle[f"{artifact_id}/baseline.json"])
    candidate = json.loads(bundle[f"{artifact_id}/candidate.json"])
    comparison = json.loads(bundle[f"{artifact_id}/comparison.json"])
    index = json.loads(bundle[f"{artifact_id}/index.json"])
    assert baseline["artifact_id"] == f"{artifact_id}-baseline"
    assert candidate["artifact_id"] == f"{artifact_id}-candidate"
    assert comparison["artifact_id"] == artifact_id
    assert comparison["baseline_artifact_id"] == baseline["artifact_id"]
    assert comparison["candidate_artifact_id"] == candidate["artifact_id"]
    assert comparison["baseline_run_id"] == record.baseline_run_id
    assert comparison["candidate_run_id"] == record.candidate_run_id
    assert comparison["population_compatibility"] == "MATCHED"
    assert comparison["verification_status"] == "UNVERIFIED"
    assert comparison["claim_scope"] == "INTEGRATION_ONLY"
    assert {a["artifact_id"] for a in index["artifacts"]} == {
        baseline["artifact_id"],
        candidate["artifact_id"],
        comparison["artifact_id"],
    }
    assert index["catalog_status"] == "EXPLICIT_ALLOWLIST"
    assert "transitions" not in json.dumps(comparison)
    assert "baseline_category" not in json.dumps(comparison)
    assert not (tmp / "local-private" / "workspaces" / ws / "exports").exists()
    assert not (tmp / artifact_id).exists()


def test_curated_bundle_drops_private_per_query_and_keeps_claim_scope(context) -> None:
    store, ws, record, _ = _make_comparison(context)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(
        ws,
        record.comparison_id,
        _classification(kind=WorkspaceExportDataKind.CURATED_DATASET),
    )
    assert preview.eligible
    artifacts = [
        json.loads(data) for data in service.get_prepared_files(ws, preview.preview_id).values()
    ]
    for entry in artifacts[:3]:
        assert entry["data_kind"] == "CURATED_DATASET"
        assert entry["claim_scope"] == "PROTOCOL_SPECIFIC"
    assert artifacts[0]["evidence"] == []
    assert artifacts[1]["evidence"] == []


def test_exploratory_is_blocked_before_public_adapter_or_serialization(
    context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, record, _ = _make_comparison(context, mode=ComparisonMode.EXPLORATORY_ONLY)

    def forbidden(*args: object, **kwargs: object):
        pytest.fail("exploratory comparison must never call public adapter/serializer")

    monkeypatch.setattr(module, "adapt_evaluation_result", forbidden)
    monkeypatch.setattr(module, "serialize_public_artifact", forbidden)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    assert not preview.eligible
    assert preview.blocking_reasons == ["NON_CANONICAL_COMPARISON"]
    assert preview.output_files == []
    with pytest.raises(LookupError):
        service.get_prepared_files(ws, preview.preview_id)


def test_not_run_is_rejected_by_public_policy(context) -> None:
    store, ws, record, _ = _make_comparison(context)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(
        ws, record.comparison_id, _classification(status=VerificationStatus.NOT_RUN)
    )
    assert not preview.eligible
    assert preview.blocking_reasons == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]


def test_mismatched_recorded_operand_hash_blocks_export(
    context, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, ws, record, _ = _make_comparison(context)
    original = store.get_run_artifacts

    def mismatched(workspace_id: str, run_id: str):
        result, provenance = original(workspace_id, run_id)
        if run_id == record.candidate_run_id:
            provenance = provenance.model_copy(update={"result_sha256": "0" * 64})
        return result, provenance

    monkeypatch.setattr(store, "get_run_artifacts", mismatched)
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    assert not preview.eligible
    assert preview.blocking_reasons == ["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"]


def test_tampered_persisted_comparison_does_not_export(context) -> None:
    store, ws, record, tmp = _make_comparison(context)
    path = (
        tmp
        / "local-private"
        / "workspaces"
        / ws
        / "comparisons"
        / record.comparison_id
        / "result.json"
    )
    path.write_bytes(path.read_bytes() + b" ")
    service = ExportService(store, clock=lambda: NOW)
    preview = service.preview_comparison(ws, record.comparison_id, _classification())
    assert not preview.eligible
    assert preview.blocking_reasons == ["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"]


def test_mutated_private_input_population_blocks_export(context) -> None:
    store, ws, record, tmp = _make_comparison(context)
    snapshot = store.get_run_snapshot(ws, record.baseline_run_id)
    path = (
        tmp
        / "local-private"
        / "workspaces"
        / ws
        / "inputs"
        / "imported"
        / f"{snapshot.ground_truth_input_id}.jsonl"
    )
    path.write_bytes(path.read_bytes() + b" ")
    preview = ExportService(store, clock=lambda: NOW).preview_comparison(
        ws, record.comparison_id, _classification()
    )
    assert not preview.eligible
    assert preview.blocking_reasons == ["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"]


def test_wrong_operand_identity_blocks_preview(context, monkeypatch: pytest.MonkeyPatch) -> None:
    store, ws, record, _ = _make_comparison(context)
    original = store.get_comparison_record

    def invalid(workspace_id: str, comparison_id: str):
        value = original(workspace_id, comparison_id)
        return value.model_copy(update={"candidate_run_id": value.baseline_run_id})

    monkeypatch.setattr(store, "get_comparison_record", invalid)
    preview = ExportService(store, clock=lambda: NOW).preview_comparison(
        ws, record.comparison_id, _classification()
    )
    assert not preview.eligible
    assert preview.blocking_reasons == ["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"]


def test_public_adapter_rejects_secret_metadata_without_leaking(
    context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, record, _ = _make_comparison(context)

    def unsafe(*args: object, **kwargs: object):
        raise ValueError("api_key: SENSITIVE_PRIVATE_VALUE /secret/path")

    monkeypatch.setattr(module, "adapt_evaluation_result", unsafe)
    preview = ExportService(store, clock=lambda: NOW).preview_comparison(
        ws, record.comparison_id, _classification()
    )
    assert not preview.eligible
    assert preview.blocking_reasons == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]
    assert "SENSITIVE_PRIVATE_VALUE" not in preview.model_dump_json()


def test_stronger_comparison_status_than_operand_rejected_by_existing_index_policy(
    context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws, record, _ = _make_comparison(context)
    original = module.adapt_evaluation_result
    count = [0]

    def weaken(*args: object, **kwargs: object):
        artifact = original(*args, **kwargs)
        count[0] += 1
        if count[0] == 1:
            return artifact.model_copy(
                update={"verification_status": VerificationStatus.UNVERIFIED}
            )
        return artifact

    monkeypatch.setattr(module, "adapt_evaluation_result", weaken)
    preview = ExportService(store, clock=lambda: NOW).preview_comparison(
        ws, record.comparison_id, _classification(status=VerificationStatus.VERIFIED)
    )
    assert not preview.eligible
    assert preview.blocking_reasons == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]


def test_invalid_comparison_id_fails_before_storage(context) -> None:
    store, ws, _, _ = context
    service = ExportService(store, clock=lambda: NOW)
    with pytest.raises(ValueError, match="invalid comparison identifier"):
        service.preview_comparison(ws, "../../private", _classification())
