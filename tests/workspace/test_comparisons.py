"""Phase 6.3 Task 4: immutable canonical and exploratory comparison boundaries."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from evalops.workspace.application.comparisons import (
    ComparisonService,
    IncompatibleComparisonError,
)
from evalops.workspace.application.runs import CreateRetrievalRun, RetrievalRunService
from evalops.workspace.comparison.models import (
    ComparisonCompatibilityStatus,
    ComparisonMode,
)
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.ingestion.service import register_imported_jsonl
from evalops.workspace.jobs.models import JobState
from evalops.workspace.storage import (
    UnknownComparisonError,
    WorkspaceStorageError,
    WorkspaceStore,
)

GT = b'{"query_id":"q1","relevant_document_ids":["d1"]}\n'
GT_CHANGED = b'{"query_id":"q1","relevant_document_ids":["d2"]}\n'
GOOD = b'{"query_id":"q1","retrieved_document_ids":["d1"]}\n'
BAD = b'{"query_id":"q1","retrieved_document_ids":["d2"]}\n'


@pytest.fixture
def prepared(
    tmp_path: Path,
) -> tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path]:
    root = tmp_path / "private"
    store = WorkspaceStore(root)
    store.initialize()
    ws = store.create_workspace("comparison tests").workspace_id
    runner = RetrievalRunService(store)
    runner.start()
    try:
        yield store, ws, runner, ComparisonService(store), root
    finally:
        runner.stop()


def _register(store: WorkspaceStore, ws: str, kind: InputKind, raw: bytes) -> str:
    return register_imported_jsonl(
        store, ws, kind=kind, data=raw, source_filename="fixture.jsonl"
    ).manifest.input_id


def _run(
    store: WorkspaceStore,
    ws: str,
    runner: RetrievalRunService,
    *,
    ground: bytes = GT,
    predictions: bytes = GOOD,
    top_k: int = 1,
    dataset: str = "same",
) -> str:
    gt = _register(store, ws, InputKind.RETRIEVAL_GROUND_TRUTH, ground)
    pred = _register(store, ws, InputKind.RETRIEVAL_PREDICTIONS, predictions)
    job = runner.create_and_enqueue(
        ws,
        CreateRetrievalRun(
            run_name="fixture",
            ground_truth_input_id=gt,
            predictions_input_id=pred,
            top_k=top_k,
            system_name="demo",
            dataset_name=dataset,
            dataset_version="v1",
        ),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = store.get_job_record(ws, job.job_id).state
        if status == JobState.COMPLETE:
            return job.run_id
        if status in {JobState.FAILED, JobState.INTERRUPTED, JobState.CANCELLED}:
            pytest.fail(f"run did not complete: {status}")
        time.sleep(0.01)
    pytest.fail("run did not complete before deadline")


def test_canonical_uses_authoritative_metric_comparison_once(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import evalops.workspace.application.comparisons as module

    store, ws, runner, service, root = prepared
    baseline = _run(store, ws, runner, predictions=GOOD)
    candidate = _run(store, ws, runner, predictions=BAD)
    pinned = service.set_baseline(ws, baseline).baseline
    assert pinned is not None

    actual = module.compare_metrics
    captured: list[tuple[object, object, object]] = []

    def spy(current: object, prior: object, rules: object):
        captured.append((current, prior, rules))
        return actual(current, prior, rules)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "compare_metrics", spy)
    record = service.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    assert len(captured) == 1
    assert record.mode == ComparisonMode.CANONICAL
    assert record.compatibility.status == ComparisonCompatibilityStatus.COMPARABLE
    assert record.baseline_run_id == baseline
    assert record.candidate_run_id == candidate
    assert record.baseline_result_sha256 == pinned.result_sha256
    assert record.regression_report == actual(*captured[0])
    assert record.regression_report.passed is False
    assert store.get_comparison_record(ws, record.comparison_id) == record
    assert WorkspaceStore(root).get_comparison_record(ws, record.comparison_id) == record
    assert store.list_comparison_records(ws) == [record]
    directory = root / "workspaces" / ws / "comparisons" / record.comparison_id
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    assert config["policy_version"] == "workspace-retrieval-regression-v1"
    assert config["mode"] == ComparisonMode.CANONICAL.value
    assert not list(root.rglob("*.tmp"))


def test_no_baseline_and_self_comparison_are_rejected_without_artifacts(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, root = prepared
    run_id = _run(store, ws, runner)
    with pytest.raises(WorkspaceStorageError, match="baseline"):
        service.create_comparison(ws, run_id, mode=ComparisonMode.CANONICAL)
    service.set_baseline(ws, run_id)
    with pytest.raises(ValueError, match="itself"):
        service.create_comparison(ws, run_id, mode=ComparisonMode.EXPLORATORY_ONLY)
    assert store.list_comparison_records(ws) == []
    assert not list((root / "workspaces" / ws).rglob("comparison-*/result.json"))


def test_canonical_rejects_incompatible_and_exploratory_is_permanently_separate(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, root = prepared
    baseline = _run(store, ws, runner, top_k=1)
    candidate = _run(store, ws, runner, top_k=2)
    service.set_baseline(ws, baseline)
    with pytest.raises(IncompatibleComparisonError) as exc:
        service.create_comparison(ws, candidate, mode=ComparisonMode.CANONICAL)
    assert "top_k" in [reason.field for reason in exc.value.compatibility.reasons]
    assert store.list_comparison_records(ws) == []
    record = service.create_comparison(ws, candidate, mode=ComparisonMode.EXPLORATORY_ONLY)
    assert record.mode == ComparisonMode.EXPLORATORY_ONLY
    assert record.compatibility.status == ComparisonCompatibilityStatus.NON_COMPARABLE
    assert store.get_comparison_record(ws, record.comparison_id) == record
    with pytest.raises(WorkspaceStorageError, match="already exists"):
        store.save_comparison_record(ws, record)
    assert (
        store.get_comparison_record(ws, record.comparison_id).mode
        == ComparisonMode.EXPLORATORY_ONLY
    )


def test_modified_ground_truth_never_allows_canonical_regression_claim(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, _ = prepared
    first = _run(store, ws, runner)
    second = _run(store, ws, runner, ground=GT_CHANGED)
    service.set_baseline(ws, first)
    with pytest.raises(IncompatibleComparisonError) as exc:
        service.create_comparison(ws, second, mode=ComparisonMode.CANONICAL)
    assert "ground_truth_population" in [r.field for r in exc.value.compatibility.reasons]


def test_comparison_snapshot_remains_unchanged_after_repinning(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, root = prepared
    first = _run(store, ws, runner)
    second = _run(store, ws, runner, predictions=BAD)
    service.set_baseline(ws, first)
    historic = service.create_comparison(ws, second, mode=ComparisonMode.CANONICAL)
    directory = root / "workspaces" / ws / "comparisons" / historic.comparison_id
    before = {name: (directory / name).read_bytes() for name in ("config.json", "result.json")}
    service.set_baseline(ws, second)
    assert store.get_comparison_record(ws, historic.comparison_id) == historic
    assert {name: (directory / name).read_bytes() for name in before} == before


def test_cross_workspace_or_tampered_evidence_cannot_create_comparison(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, root = prepared
    first = _run(store, ws, runner)
    second = _run(store, ws, runner)
    service.set_baseline(ws, first)
    foreign = store.create_workspace("foreign").workspace_id
    with pytest.raises(WorkspaceStorageError):
        service.create_comparison(foreign, second, mode=ComparisonMode.CANONICAL)
    path = root / "workspaces" / ws / "runs" / second / "result.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(WorkspaceStorageError, match="checksum"):
        service.create_comparison(ws, second, mode=ComparisonMode.CANONICAL)
    assert store.list_comparison_records(ws) == []


def test_comparison_result_mutation_and_symlink_fail_closed(
    prepared: tuple[WorkspaceStore, str, RetrievalRunService, ComparisonService, Path],
) -> None:
    store, ws, runner, service, root = prepared
    first = _run(store, ws, runner)
    second = _run(store, ws, runner, predictions=BAD)
    service.set_baseline(ws, first)
    record = service.create_comparison(ws, second, mode=ComparisonMode.CANONICAL)
    directory = root / "workspaces" / ws / "comparisons" / record.comparison_id
    result_path = directory / "result.json"
    original = result_path.read_bytes()
    result_path.write_bytes(original + b"\n")
    with pytest.raises(WorkspaceStorageError, match="checksum"):
        store.get_comparison_record(ws, record.comparison_id)
    result_path.write_bytes(original)

    config_path = directory / "config.json"
    backup = config_path.read_bytes()
    config_path.unlink()
    target = root / "target.json"
    target.write_bytes(backup)
    try:
        config_path.symlink_to(target)
    except OSError:
        pytest.skip("symlink privileges unavailable")
    with pytest.raises(UnknownComparisonError):
        store.get_comparison_record(ws, record.comparison_id)
