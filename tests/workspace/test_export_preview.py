"""Phase 6.4 Task 1: exact serialized in-memory preview, never implicit publication."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import evalops.workspace.application.exports as module
from evalops.export.adapters import adapt_evaluation_result
from evalops.export.models import (
    ClaimScope,
    DataKind,
    VerificationStatus,
)
from evalops.export.serialization import serialize_public_artifact
from evalops.models.runs import EvaluationResult, RunConfig
from evalops.workspace.application.exports import ExportService
from evalops.workspace.export.models import (
    ExportClassification,
    WorkspaceExportDataKind,
)
from evalops.workspace.storage import WorkspaceStorageError

RUN_ID = "run-" + "a" * 32
WORKSPACE_ID = "ws-" + "b" * 32
NOW = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)


class FixtureStore:
    """Minimal completed-run read boundary; no persistent preview storage."""

    def __init__(self, result: EvaluationResult) -> None:
        self.result = result
        self.reads: list[tuple[str, str]] = []

    def get_run_artifacts(self, workspace_id: str, run_id: str) -> tuple[EvaluationResult, None]:
        self.reads.append((workspace_id, run_id))
        if workspace_id != WORKSPACE_ID or run_id != RUN_ID:
            raise WorkspaceStorageError("Sensitive /private/path")
        return self.result, None


@pytest.fixture
def result(tmp_path: Path) -> EvaluationResult:
    return EvaluationResult(
        evaluation_type="retrieval",
        run=RunConfig(
            run_id=RUN_ID,
            dataset_name="synthetic-fixture",
            dataset_version="v1",
            system_name="retriever",
            top_k=2,
            evaluator_versions={"retrieval": "deterministic-v1"},
            timestamp=NOW,
        ),
        metrics={"recall_at_2": 1.0, "mrr": 0.5},
        details={
            "private_input_file": str(tmp_path / "raw-predictions.jsonl"),
            "private_session": "bootstrap=SENSITIVE",
            "per_query": {
                "q1": {
                    "metrics": {"mrr": 0.5},
                    "retrieved_document_ids": ["d2", "d1"],
                    "relevant_document_ids": ["d1"],
                    "failure_category": "PASS",
                }
            },
        },
    )


def classification(
    kind: WorkspaceExportDataKind = WorkspaceExportDataKind.SYNTHETIC_FIXTURE,
    status: VerificationStatus = VerificationStatus.UNVERIFIED,
) -> ExportClassification:
    return ExportClassification(
        verification_status=status,
        data_kind=kind,
        limitations=["Local-only evaluation with no external validation"],
    )


def test_preview_uses_authoritative_adapter_and_exact_canonical_bytes(
    result: EvaluationResult, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FixtureStore(result)
    service = ExportService(store, clock=lambda: NOW)  # type: ignore[arg-type]
    calls: list[str] = []

    def tracked_adapter(*args: object, **kwargs: object):
        calls.append("adapter")
        return adapt_evaluation_result(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_serializer(artifact: object):
        calls.append("serializer")
        return serialize_public_artifact(artifact)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "adapt_evaluation_result", tracked_adapter)
    monkeypatch.setattr(module, "serialize_public_artifact", tracked_serializer)
    chosen = classification()
    preview = service.preview_run(WORKSPACE_ID, RUN_ID, chosen)
    assert calls == ["adapter", "serializer"]
    assert store.reads == [(WORKSPACE_ID, RUN_ID)]
    assert preview.eligible and preview.blocking_reasons == []
    assert preview.source_type == "run"
    assert preview.classification == chosen
    assert preview.expires_at == NOW + timedelta(minutes=15)
    assert "Validated synthetic per-query evidence" in preview.included
    assert len(preview.output_files) == 1

    files = service.get_prepared_files(WORKSPACE_ID, preview.preview_id)
    filename = "workspace-" + RUN_ID + ".json"
    assert list(files) == [filename]
    expected = serialize_public_artifact(
        adapt_evaluation_result(
            result,
            artifact_id="workspace-" + RUN_ID,
            verification_status=chosen.verification_status,
            data_kind=DataKind.SYNTHETIC_FIXTURE,
            claim_scope=ClaimScope.INTEGRATION_ONLY,
            limitations=chosen.limitations,
        )
    ).encode("utf-8")
    assert files[filename] == expected
    assert preview.output_files[0].sha256 == hashlib.sha256(expected).hexdigest()
    assert preview.output_files[0].size_bytes == len(expected)
    assert str(tmp_path) not in files[filename].decode("utf-8")
    for private_text in (
        "private_input_file",
        "private_session",
        "bootstrap",
        "raw-predictions.jsonl",
        "source_path",
        "job_id",
        "session_token",
    ):
        assert private_text not in files[filename].decode("utf-8")
    assert not list(tmp_path.iterdir()), "Preview must not persist any file before confirmation"


def test_curated_classification_suppresses_per_query_and_is_protocol_specific(
    result: EvaluationResult,
) -> None:
    service = ExportService(FixtureStore(result), clock=lambda: NOW)  # type: ignore[arg-type]
    preview = service.preview_run(
        WORKSPACE_ID, RUN_ID, classification(WorkspaceExportDataKind.CURATED_DATASET)
    )
    assert preview.eligible
    assert "Validated synthetic per-query evidence" not in preview.included
    artifact = json.loads(
        next(iter(service.get_prepared_files(WORKSPACE_ID, preview.preview_id).values()))
    )
    assert artifact["data_kind"] == "CURATED_DATASET"
    assert artifact["claim_scope"] == "PROTOCOL_SPECIFIC"
    assert artifact["verification_status"] == "UNVERIFIED"
    assert artifact["evidence"] == []
    assert "private_input_file" not in json.dumps(artifact)


def test_not_run_is_blocked_by_existing_public_policy(result: EvaluationResult) -> None:
    service = ExportService(FixtureStore(result), clock=lambda: NOW)  # type: ignore[arg-type]
    preview = service.preview_run(
        WORKSPACE_ID, RUN_ID, classification(status=VerificationStatus.NOT_RUN)
    )
    assert not preview.eligible
    assert preview.output_files == []
    assert preview.blocking_reasons == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]
    with pytest.raises(LookupError):
        service.get_prepared_files(WORKSPACE_ID, preview.preview_id)


@pytest.mark.parametrize(
    "unsafe_dataset",
    ["C:\\Users\\private\\file.jsonl", "/home/user/private.jsonl", "api_key: secretvalue"],
)
def test_unsafe_public_metadata_rejected_without_leaking_values(
    result: EvaluationResult,
    unsafe_dataset: str,
) -> None:
    poisoned = result.model_copy(
        update={"run": result.run.model_copy(update={"dataset_name": unsafe_dataset})}
    )
    service = ExportService(FixtureStore(poisoned), clock=lambda: NOW)  # type: ignore[arg-type]
    preview = service.preview_run(WORKSPACE_ID, RUN_ID, classification())
    assert not preview.eligible
    assert preview.output_files == []
    assert preview.blocking_reasons == ["PUBLIC_EVIDENCE_POLICY_REJECTED"]
    assert unsafe_dataset not in preview.model_dump_json()


def test_only_allowed_data_kinds_and_explicit_owner_status() -> None:
    with pytest.raises(ValidationError):
        ExportClassification.model_validate(
            {
                "data_kind": "OFFICIAL_BENCHMARK",
                "verification_status": "VERIFIED",
            }
        )
    with pytest.raises(ValidationError):
        ExportClassification.model_validate({"data_kind": "SYNTHETIC_FIXTURE"})
    with pytest.raises(ValidationError):
        ExportClassification.model_validate(
            {
                "data_kind": "SYNTHETIC_FIXTURE",
                "verification_status": "UNVERIFIED",
                "claim_scope": "BENCHMARK_RESULT",
            }
        )


def test_preview_is_expiring_and_workspace_scoped(result: EvaluationResult) -> None:
    clock = [NOW]
    service = ExportService(FixtureStore(result), clock=lambda: clock[0])  # type: ignore[arg-type]
    preview = service.preview_run(WORKSPACE_ID, RUN_ID, classification())
    with pytest.raises(LookupError):
        service.get_prepared_files("ws-" + "c" * 32, preview.preview_id)
    assert service.get_prepared_files(WORKSPACE_ID, preview.preview_id)
    clock[0] = NOW + timedelta(minutes=15)
    with pytest.raises(LookupError):
        service.get_prepared_files(WORKSPACE_ID, preview.preview_id)


def test_storage_failure_returns_safe_block_without_preparing(
    result: EvaluationResult,
) -> None:
    service = ExportService(FixtureStore(result), clock=lambda: NOW)  # type: ignore[arg-type]
    preview = service.preview_run(WORKSPACE_ID, "run-" + "f" * 32, classification())
    assert not preview.eligible
    assert preview.blocking_reasons == ["SOURCE_EVIDENCE_UNAVAILABLE_OR_INVALID"]
    assert "/private/path" not in preview.model_dump_json()
    with pytest.raises(LookupError):
        service.get_prepared_files(WORKSPACE_ID, preview.preview_id)
