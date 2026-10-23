"""Phase 6.3 Task 2: strict population compatibility and claim-safety contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from evalops.models.runs import EvaluationResult, RunConfig
from evalops.workspace.application.runs import (
    CreateRetrievalRun,
    RunSnapshot,
    create_retrieval_run,
)
from evalops.workspace.comparison.compatibility import (
    assess_local_retrieval_compatibility,
    canonical_population_evidence,
    load_verified_population,
)
from evalops.workspace.comparison.models import ComparisonCompatibilityStatus
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore


def make_operand(
    run_id: str,
    *,
    config_updates: dict[str, Any] | None = None,
    result_type: str = "retrieval",
    truth_hash: str = "a" * 64,
    prediction_hash: str = "b" * 64,
    prediction_count: int = 2,
) -> tuple[RunSnapshot, EvaluationResult]:
    config = RunConfig(
        run_id=run_id,
        dataset_name="SENSITIVE-private-dataset",
        dataset_version="v1",
        system_name=f"system-{run_id}",
        top_k=2,
        evaluator_versions={"retrieval": "deterministic-v1"},
    )
    if config_updates:
        config = config.model_copy(update=config_updates)
    snapshot = RunSnapshot(
        run_id=run_id,
        workspace_id="ws-" + "1" * 32,
        run_name="private test",
        ground_truth_input_id="input-" + "1" * 32,
        ground_truth_content_sha256=truth_hash,
        predictions_input_id="input-" + "2" * 32,
        predictions_content_sha256=prediction_hash,
        config=config,
        created_at=datetime.now(UTC),
    )
    result = EvaluationResult(
        evaluation_type=result_type,
        run=config,
        metrics={"mrr": 1.0},
        details={"prediction_query_count": prediction_count},
    )
    return snapshot, result


def compare(
    left: tuple[RunSnapshot, EvaluationResult],
    right: tuple[RunSnapshot, EvaluationResult],
    *,
    baseline_gt: dict[str, list[str]] | None = None,
    candidate_gt: dict[str, list[str]] | None = None,
    baseline_pred: dict[str, list[str]] | None = None,
    candidate_pred: dict[str, list[str]] | None = None,
):
    gt_left = baseline_gt or {"q1": ["doc1"], "q2": ["doc2"]}
    gt_right = candidate_gt or {"q1": ["doc1"], "q2": ["doc2"]}
    pred_left = baseline_pred if baseline_pred is not None else {"q1": ["doc1"], "q2": []}
    pred_right = candidate_pred if candidate_pred is not None else {"q1": [], "q2": ["other"]}
    return assess_local_retrieval_compatibility(
        *left,
        *right,
        baseline_population=canonical_population_evidence(gt_left, pred_left),
        candidate_population=canonical_population_evidence(gt_right, pred_right),
    )


def test_equivalent_reordered_ground_truth_and_changed_predictions_are_comparable() -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand("run-" + "b" * 32, truth_hash="c" * 64, prediction_hash="d" * 64)
    result = compare(
        a,
        b,
        baseline_gt={"q1": ["doc1", "doc2"], "q2": ["doc3"]},
        candidate_gt={"q2": ["doc3"], "q1": ["doc2", "doc1"]},
    )
    assert result.status == ComparisonCompatibilityStatus.COMPARABLE
    assert result.reasons == []


@pytest.mark.parametrize(
    ("field", "candidate"),
    [
        ("dataset_name", "private-other"),
        ("dataset_version", "v2"),
        ("dataset_revision", "rev2"),
        ("benchmark", "new-benchmark"),
        ("language", "th"),
        ("split", "dev"),
        ("top_k", 3),
        ("evaluator_versions", {"retrieval": "deterministic-v2"}),
        ("annotation_policy", "new-policy"),
        ("quality_filter", ["only-reviewed"]),
        ("evaluator_config", {"cutoff": 0.5}),
    ],
)
def test_config_dimension_mismatches_fail_closed(field: str, candidate: Any) -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand("run-" + "b" * 32, config_updates={field: candidate})
    result = compare(a, b)
    assert result.status == ComparisonCompatibilityStatus.NON_COMPARABLE
    assert field in [reason.field for reason in result.reasons]


def test_different_relevance_or_query_population_is_not_comparable() -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand("run-" + "b" * 32)
    changed = compare(a, b, candidate_gt={"q1": ["other"], "q2": ["doc2"]})
    partial = compare(a, b, candidate_gt={"q1": ["doc1"]})
    assert "ground_truth_population" in [r.field for r in changed.reasons]
    assert "query_population" in [r.field for r in partial.reasons]


@pytest.mark.parametrize("keyset", [{"q1": ["doc1"]}, {"q1": [], "q2": [], "extra": []}])
def test_missing_or_extra_prediction_queries_never_claim_comparability(
    keyset: dict[str, list[str]],
) -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand("run-" + "b" * 32, prediction_count=len(keyset))
    result = compare(a, b, candidate_pred=keyset)
    assert "candidate_prediction_coverage" in [r.field for r in result.reasons]


def test_missing_or_untrusted_population_evidence_fails_closed() -> None:
    left = make_operand("run-" + "a" * 32)
    right = make_operand("run-" + "b" * 32)
    result = assess_local_retrieval_compatibility(*left, *right)
    assert result.status == ComparisonCompatibilityStatus.NON_COMPARABLE
    assert "verified_population" in [r.field for r in result.reasons]


def test_non_retrieval_or_inconsistent_result_identity_rejected() -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand("run-" + "b" * 32, result_type="generation")
    result = compare(a, b)
    assert {"evaluation_type", "retrieval_only"}.issubset({r.field for r in result.reasons})

    snapshot, output = a
    forged = output.model_copy(
        update={"run": output.run.model_copy(update={"run_id": "different"})}
    )
    result = compare((snapshot, forged), b)
    assert "baseline_result_identity" in [r.field for r in result.reasons]


def test_all_reasons_are_sorted_and_no_private_content_is_rendered() -> None:
    a = make_operand("run-" + "a" * 32)
    b = make_operand(
        "run-" + "b" * 32,
        config_updates={
            "dataset_name": "C:/Users/secret",
            "top_k": 4,
            "quality_filter": ["SECRET"],
        },
    )
    result = compare(a, b, candidate_gt={"q1": ["other"]})
    fields = [r.field for r in result.reasons]
    assert fields == sorted(fields)
    assert "SENSITIVE" not in result.model_dump_json()
    assert "secret" not in result.model_dump_json().lower()
    assert "SECRET" not in result.model_dump_json()


def test_population_loading_uses_owned_hash_checked_input_bytes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("verified").workspace_id
    truth = (
        b'{"query_id":"q2","relevant_document_ids":["d2"]}\n'
        b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
    )
    pred = (
        b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
        b'{"query_id":"q2","retrieved_document_ids":[]}\n'
    )
    gt_id = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_GROUND_TRUTH, data=truth, source_filename="gt.jsonl"
    ).manifest.input_id
    pred_id = register_imported_jsonl(
        store, ws, kind=InputKind.RETRIEVAL_PREDICTIONS, data=pred, source_filename="pred.jsonl"
    ).manifest.input_id
    snapshot = create_retrieval_run(
        store,
        ws,
        CreateRetrievalRun(
            run_name="candidate",
            ground_truth_input_id=gt_id,
            predictions_input_id=pred_id,
            top_k=2,
            system_name="test",
            dataset_name="safe",
            dataset_version="v1",
        ),
    )
    evidence = load_verified_population(store, snapshot)
    assert evidence == canonical_population_evidence(
        {"q1": ["d1"], "q2": ["d2"]}, {"q1": ["d1"], "q2": []}
    )

    imported_path = root / "workspaces" / ws / "inputs" / "imported" / f"{gt_id}.jsonl"
    imported_path.write_bytes(imported_path.read_bytes() + b"\n")
    with pytest.raises(WorkspaceStorageError):
        load_verified_population(store, snapshot)
