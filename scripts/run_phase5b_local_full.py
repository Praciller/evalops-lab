"""Run the authorized full RAGTruth local Qwen3 classification benchmark.

The runner is deliberately sequential and resumable.  It writes only safe
per-call traces to ignored local state and never persists source text, model
output, reasoning, or credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace, LLMJudgeEvaluator
from evalops.evaluators.judge.models import (
    JudgeClassificationDecision,
    parse_classification_judge_payload,
)
from evalops.evaluators.judge.prompt import (
    CLASSIFICATION_OUTPUT_SCHEMA,
    CLASSIFICATION_SCHEMA_VERSION,
    CLASSIFICATION_TRANSPORT_PROMPT_SHA256,
    CLASSIFICATION_TRANSPORT_VERSION,
    JUDGE_PROMPT_SHA256,
    JUDGE_PROMPT_VERSION,
    render_classification_judge_prompt,
)
from evalops.evaluators.judge.providers import (
    JudgeOutputMode,
    OllamaJudgeConfig,
    OllamaProviderAdapter,
    SamplingConfig,
    schema_sha256,
)
from evalops.models.hallucination import AnnotationPolicy
from evalops.pilot.analysis import (
    build_local_three_evaluator_analysis,
    compare_pilot_predictions,
    summarize_provider_records,
)
from evalops.pilot.execution import PilotStateStore, RequestBudget, run_provider_pilot
from evalops.pilot.full_analysis import bootstrap_confidence_intervals, summarize_full_predictions
from evalops.pilot.models import PilotExampleMetadata, PilotManifest, PilotRunRecord
from evalops.pilot.provenance import ModelVersionChangedError, ModelVersionContinuity

try:
    from scripts.run_phase5a_local_pilot import (
        _artifact_predictions,
        _ollama_metadata,
    )
except ImportError:
    from run_phase5a_local_pilot import _artifact_predictions, _ollama_metadata


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PROVIDER = "local-ollama"
EXPERIMENT_ID = "ragtruth-local-llm-judge-full-v1"
FULL_MANIFEST_ID = "ragtruth-llm-judge-full-manifest-v1"
MODEL = "qwen3:8b"
EXPECTED_OLLAMA_ID = "500a1f067a9f"
EXPECTED_WEIGHTS_DIGEST = "sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f"
EXPECTED_MODEL_DIGEST = f"ollama-id:{EXPECTED_OLLAMA_ID};weights:{EXPECTED_WEIGHTS_DIGEST}"
NUM_PREDICT = 128
FULL_SIZE = 2675
BOOTSTRAP_SEED = 20260830
BOOTSTRAP_REPLICATES = 10_000
EXPECTED_SOURCE_REVISION = "c103204b9ce28d6bbad859304bf30de72b8ed8fe"
EXPECTED_RESPONSE_SHA256 = "e4c2e4ac24fff676d8984cc61c35d791612fadc58015335d97dd632375e18073"
EXPECTED_SOURCE_SHA256 = "0dffc26ea9f3c1c3d7c7e8336b56ef1646e3cec876edffcca3c9c624d12d578b"
V3_REPORT = REPO_ROOT / "reports" / "phase5a-local-pilot-v3.json"
DEFAULT_DATA_DIR = REPO_ROOT / "datasets" / "external" / "ragtruth"
DEFAULT_STATE = REPO_ROOT / "reports" / "phase5b-local-full-v1-state.json"
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase5b-local-full-v1.json"
DEFAULT_PREFLIGHT = REPO_ROOT / "reports" / "phase5b-local-full-preflight.json"
HEURISTIC_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-heuristic-v1.json"
HHEM_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-hhem-v1.json"


class FullRunTechnicalReliabilityRegression(RuntimeError):
    """Raised when terminal failures cross the authorized full-run circuit breaker."""


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _assert_clean_source_tree() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    if result.stdout.strip():
        raise RuntimeError("LOCAL_SOURCE_WORKTREE_NOT_CLEAN")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _transport_config() -> OllamaJudgeConfig:
    return OllamaJudgeConfig(
        model=MODEL,
        model_digest=EXPECTED_MODEL_DIGEST,
        output_mode=JudgeOutputMode.JSON_SCHEMA_STRICT,
        temperature=0.0,
        top_p=1.0,
        num_predict=NUM_PREDICT,
        num_ctx=None,
        think=False,
        stream=False,
        keep_alive=None,
        transport_version=CLASSIFICATION_TRANSPORT_VERSION,
        schema_hash=schema_sha256(CLASSIFICATION_OUTPUT_SCHEMA),
        semantic_prompt_hash=JUDGE_PROMPT_SHA256,
    )


def _sampling() -> SamplingConfig:
    return SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=NUM_PREDICT,
        reasoning_effort="low",
        include_reasoning=False,
    )


def _evaluator(metadata: Mapping[str, object]) -> LLMJudgeEvaluator:
    context_length = metadata.get("context_length")
    config = _transport_config()
    provider = OllamaProviderAdapter(
        timeout_seconds=300.0,
        judge_config=config,
        quantization=str(metadata.get("quantization")),
        parameter_size=str(metadata.get("parameter_size")),
        context_length=context_length if isinstance(context_length, int) else None,
        inference_device="cpu",
        thinking_mode="OFF",
        ollama_version=str(metadata.get("ollama_version")),
    )
    return LLMJudgeEvaluator(
        provider,
        sampling=_sampling(),
        prompt_renderer=render_classification_judge_prompt,
        output_schema=CLASSIFICATION_OUTPUT_SCHEMA,
        prompt_version=JUDGE_PROMPT_VERSION,
        prompt_sha256=JUDGE_PROMPT_SHA256,
        schema_version=CLASSIFICATION_SCHEMA_VERSION,
        parser=parse_classification_judge_payload,
        evaluator_version=CLASSIFICATION_SCHEMA_VERSION,
        transport_prompt_version=CLASSIFICATION_TRANSPORT_VERSION,
        transport_prompt_sha256=CLASSIFICATION_TRANSPORT_PROMPT_SHA256,
    )


def _load_dataset(data_dir: Path):
    preparation = json.loads((data_dir / "preparation-manifest.json").read_text(encoding="utf-8"))
    return load_ragtruth_dataset(
        data_dir / "response.jsonl",
        data_dir / "source_info.jsonl",
        split="test",
        source_revision=str(preparation.get("source_revision", "unknown")),
    )


def _verify_model() -> dict[str, object]:
    metadata = _ollama_metadata(MODEL)
    if (
        metadata.get("requested_model") != MODEL
        or metadata.get("returned_model") != MODEL
        or metadata.get("ollama_id") != EXPECTED_OLLAMA_ID
        or metadata.get("weights_digest") != EXPECTED_WEIGHTS_DIGEST
        or metadata.get("model_digest") != EXPECTED_MODEL_DIGEST
        or metadata.get("ollama_version") != "ollama version is 0.33.2"
    ):
        raise RuntimeError("LOCAL_MODEL_DIGEST_MISMATCH")
    return metadata


def _included_examples(dataset: Any) -> list[Any]:
    return [example for example in dataset.examples if example.quality == "good"]


def _validate_population(data_dir: Path, dataset: Any) -> dict[str, Any]:
    preparation = json.loads((data_dir / "preparation-manifest.json").read_text(encoding="utf-8"))
    response_path = data_dir / "response.jsonl"
    source_path = data_dir / "source_info.jsonl"
    included = _included_examples(dataset)
    excluded = [example for example in dataset.examples if example.quality != "good"]
    checks = {
        "preparation_mode": preparation.get("mode") == "full-prepared",
        "source_revision": preparation.get("source_revision") == EXPECTED_SOURCE_REVISION,
        "response_checksum": _sha256(response_path) == EXPECTED_RESPONSE_SHA256,
        "source_checksum": _sha256(source_path) == EXPECTED_SOURCE_SHA256,
        "test_total": len(dataset.examples) == 2700,
        "included_good": len(included) == FULL_SIZE,
        "excluded_total": len(excluded) == 25,
        "excluded_quality_counts": {
            "incorrect_refusal": sum(item.quality == "incorrect_refusal" for item in excluded),
            "truncated": sum(item.quality == "truncated" for item in excluded),
        }
        == {"incorrect_refusal": 24, "truncated": 1},
        "validation_issues": len(dataset.validation_issues) == 0,
        "unique_included_ids": len({item.example_id for item in included}) == FULL_SIZE,
    }
    if not all(value is True for key, value in checks.items() if key != "excluded_quality_counts"):
        raise RuntimeError("RAGTRUTH_FULL_POPULATION_INTEGRITY_FAILED")
    if not checks["excluded_quality_counts"]:
        raise RuntimeError("RAGTRUTH_FULL_EXCLUSION_INTEGRITY_FAILED")
    return {
        "status": "PASS",
        "source_revision": dataset.source_revision,
        "test_total": len(dataset.examples),
        "included": len(included),
        "excluded": len(excluded),
        "excluded_quality_counts": {"incorrect_refusal": 24, "truncated": 1},
        "validation_issue_count": len(dataset.validation_issues),
        "checks": checks,
    }


def _validate_v3_report() -> dict[str, Any]:
    if not V3_REPORT.is_file():
        raise RuntimeError("V3_REPORT_NOT_FOUND")
    report = json.loads(V3_REPORT.read_text(encoding="utf-8"))
    config = _transport_config()
    required = {
        "experiment_id": "ragtruth-local-llm-judge-pilot-v3",
        "status": "COMPLETE",
        "pilot_completed": True,
        "successful_at_end": 120,
        "pilot_id_match": True,
        "leakage_check": "PASS",
        "model": MODEL,
        "model_version": EXPECTED_MODEL_DIGEST,
        "local_model_digest": EXPECTED_MODEL_DIGEST,
        "primary_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "primary_schema_hash": config.schema_hash,
        "semantic_prompt_version": JUDGE_PROMPT_VERSION,
        "semantic_prompt_hash": JUDGE_PROMPT_SHA256,
        "transport_version": CLASSIFICATION_TRANSPORT_VERSION,
        "transport_hash": config.transport_hash(),
        "transport_prompt_hash": CLASSIFICATION_TRANSPORT_PROMPT_SHA256,
        "phase5b_full_run_started": False,
    }
    if any(report.get(key) != value for key, value in required.items()):
        raise RuntimeError("V3_PROVENANCE_GATE_FAILED")
    consistency = report.get("consistency")
    if not isinstance(consistency, dict) or consistency.get("status") != "COMPLETE":
        raise RuntimeError("V3_CONSISTENCY_REFERENCE_INVALID")
    if consistency.get("example_count") != 12 or consistency.get("local_requests_used") != 24:
        raise RuntimeError("V3_CONSISTENCY_REFERENCE_INVALID")
    if consistency.get("primary_prediction_unchanged") is not True:
        raise RuntimeError("V3_CONSISTENCY_PRIMARY_MUTATION")
    return {
        "status": "PASS",
        "report": "reports/phase5a-local-pilot-v3.json",
        "experiment_id": report["experiment_id"],
        "successful_at_end": report["successful_at_end"],
        "consistency_example_count": consistency["example_count"],
        "consistency_agreement_rate": consistency["three_run_label_agreement_rate"],
        "consistency_unanimous_rate": consistency["unanimous_agreement_rate"],
        "consistency_reference_identity": "verified; primary prediction unchanged",
    }


def _validate_baselines(dataset: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    included = _included_examples(dataset)
    expected_ids = {example.example_id for example in included}
    human = {
        example.example_id: example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS)
        for example in included
    }
    baseline: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    for name, path in (("heuristic", HEURISTIC_ARTIFACT), ("hhem", HHEM_ARTIFACT)):
        predictions = _artifact_predictions(path, expected_ids)
        report = json.loads(path.read_text(encoding="utf-8"))
        per_example = report.get("details", {}).get("per_example", {})
        if set(predictions) != expected_ids or len(per_example) != FULL_SIZE:
            raise RuntimeError(f"{name.upper()}_FULL_ID_MATCH_FAILED")
        for example_id, record in per_example.items():
            if record.get("human_label") != human[example_id].value:
                raise RuntimeError(f"{name.upper()}_HUMAN_LABEL_MISMATCH")
        baseline[name] = predictions
        provenance[name] = {
            "artifact": str(path.relative_to(REPO_ROOT)),
            "run_id": report.get("run", {}).get("run_id"),
            "dataset_revision": report.get("run", {}).get("dataset_revision"),
            "included": report.get("details", {}).get("counts", {}).get("included"),
            "excluded": report.get("details", {}).get("counts", {}).get("excluded"),
            "id_match": True,
        }
    return baseline, provenance


def _build_manifest(dataset: Any) -> PilotManifest:
    records = [
        PilotExampleMetadata(
            example_id=example.example_id,
            source_id=example.source_id,
            task_type=example.task_type,
            human_label=example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS),
            stratum=f"{example.task_type}:{example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS).value}",
        )
        for example in _included_examples(dataset)
    ]
    return PilotManifest(
        pilot_id=EXPERIMENT_ID,
        manifest_version=FULL_MANIFEST_ID,
        dataset_revision=EXPECTED_SOURCE_REVISION,
        split="test",
        quality_filter=["good"],
        sampling_seed=0,
        sampling_strategy="official-full-test-good-population-no-sampling-v1",
        records=records,
    )


def _examples_and_metadata(
    dataset: Any, manifest: PilotManifest
) -> tuple[
    dict[str, tuple[str, str]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, int]],
]:
    by_id = {example.example_id: example for example in dataset.examples}
    examples: dict[str, tuple[str, str]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    lengths: dict[str, dict[str, int]] = {}
    for record in manifest.records:
        example = by_id.get(record.example_id)
        if example is None or example.quality != "good" or example.split != "test":
            raise RuntimeError(f"FULL_EXAMPLE_OUTSIDE_POPULATION={record.example_id}")
        if example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS) is not record.human_label:
            raise RuntimeError(f"FULL_HUMAN_LABEL_MISMATCH={record.example_id}")
        examples[record.example_id] = (example.source_context, example.response)
        metadata[record.example_id] = {
            "task_type": example.task_type,
            "model": example.model or "unknown",
            "source_id": example.source_id,
        }
        lengths[record.example_id] = {
            "response_chars": len(example.response),
            "source_context_chars": len(example.source_context),
        }
    for example_id, value in examples.items():
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise RuntimeError(f"FULL_PROMPT_LEAKAGE_GUARD_FAILED={example_id}")
    return examples, metadata, lengths


def _state_records(state: PilotStateStore, example_ids: Sequence[str]) -> list[PilotRunRecord]:
    return [
        record
        for example_id in example_ids
        if (record := state.get(LOCAL_PROVIDER, example_id)) is not None
    ]


def _record_predictions(records: Sequence[PilotRunRecord]) -> dict[str, Any]:
    return {
        record.example_id: record.trace.prediction
        for record in records
        if record.status == "SUCCESS" and record.trace.prediction is not None
    }


def _baseline_summaries(
    baseline: Mapping[str, Mapping[str, Any]],
    ground_truth: Mapping[str, Any],
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for name, predictions in baseline.items():
        report = evaluate_hallucination_predictions(
            ground_truth, list(predictions.values()), metadata=metadata
        )
        slices: dict[str, dict[str, Any]] = {}
        for dimension, values in report.slices.items():
            slices[dimension] = {
                value: {
                    "total": sum(
                        str(item.get(dimension, "unknown")) == value for item in metadata.values()
                    ),
                    "metrics": metrics,
                }
                for value, metrics in values.items()
            }
        summaries[name] = {
            "example_count": len(predictions),
            "confusion_matrix": report.confusion_matrix.model_dump(mode="json"),
            "metrics": report.metrics,
            "false_positive_ids": report.false_positive_ids,
            "false_negative_ids": report.false_negative_ids,
            "slices": slices,
        }
    return summaries


def _validate_existing_state(state: PilotStateStore, expected_ids: set[str]) -> None:
    if not state.path.is_file():
        return
    payload = json.loads(state.path.read_text(encoding="utf-8"))
    raw_records = payload.get("records", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_records, dict):
        raise RuntimeError("FULL_STATE_INVALID")
    for key, raw in raw_records.items():
        if not isinstance(key, str) or not key.startswith(f"{LOCAL_PROVIDER}:"):
            raise RuntimeError("FULL_STATE_EXPERIMENT_MIX")
        example_id = key.split(":", 1)[1]
        if example_id not in expected_ids or not isinstance(raw, dict):
            raise RuntimeError("FULL_STATE_ID_MISMATCH")
    config = _transport_config()
    for example_id in expected_ids:
        record = state.get(LOCAL_PROVIDER, example_id)
        if record is None or record.status != "SUCCESS":
            continue
        prediction = record.trace.prediction
        if (
            prediction is None
            or record.trace.model_version != EXPECTED_MODEL_DIGEST
            or record.trace.returned_model != MODEL
            or prediction.evaluator_config.get("transport_hash") != config.transport_hash()
            or prediction.evaluator_config.get("prompt_sha256") != JUDGE_PROMPT_SHA256
            or prediction.evaluator_config.get("schema_version") != CLASSIFICATION_SCHEMA_VERSION
        ):
            raise RuntimeError("FULL_SUCCESS_IMMUTABILITY_PROVENANCE_FAILED")


def _confidence_by_id(records: Sequence[PilotRunRecord]) -> dict[str, float]:
    return {
        record.example_id: record.trace.decision.confidence
        for record in records
        if record.trace.decision is not None
        and isinstance(record.trace.decision, JudgeClassificationDecision)
    }


def _performance_summary(
    records: Sequence[PilotRunRecord], runtime_seconds: float
) -> dict[str, Any]:
    usages = [record.trace.usage or {} for record in records]
    eval_durations = [
        float(usage["eval_duration_ns"])
        for usage in usages
        if isinstance(usage.get("eval_duration_ns"), (int, float))
    ]
    completion_tokens = sum(
        float(usage.get("completion_tokens", 0))
        for usage in usages
        if isinstance(usage.get("completion_tokens"), (int, float))
    )
    latencies = [
        record.trace.latency_ms for record in records if record.trace.latency_ms is not None
    ]
    return {
        "runtime_seconds": round(runtime_seconds, 2),
        "request_count": len(records),
        "completion_tokens": completion_tokens,
        "eval_duration_seconds": sum(eval_durations) / 1_000_000_000,
        "tokens_per_second": (
            completion_tokens / (sum(eval_durations) / 1_000_000_000) if eval_durations else None
        ),
        "latency_ms": {
            "count": len(latencies),
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "p50": (
                sorted(latencies)[max(0, (len(latencies) + 1) // 2 - 1)] if latencies else None
            ),
            "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95 + 0.999999) - 1)]
            if latencies
            else None,
        },
        "load_time_ms": {
            "count": sum("load_duration_ns" in usage for usage in usages),
            "mean": (
                sum(
                    float(usage["load_duration_ns"])
                    for usage in usages
                    if "load_duration_ns" in usage
                )
                / 1_000_000
                / sum("load_duration_ns" in usage for usage in usages)
                if any("load_duration_ns" in usage for usage in usages)
                else None
            ),
        },
        "api_hosted_inference_cost_usd": 0.0,
        "electricity_cost": "NOT_ESTIMATED",
        "peak_ram_vram": "UNAVAILABLE",
    }


def _v3_delta(full_metrics: Mapping[str, float]) -> dict[str, Any]:
    v3 = json.loads(V3_REPORT.read_text(encoding="utf-8"))
    pilot_metrics = v3["local_llm_results"]["metrics"]
    return {
        "full_example_count": FULL_SIZE,
        "pilot_example_count": v3["pilot_size"],
        "full_minus_pilot": {
            name: float(full_metrics[name]) - float(pilot_metrics[name])
            for name in sorted(set(full_metrics) & set(pilot_metrics))
        },
        "pilot_metric_validity": v3["metric_validity"],
        "interpretation": (
            "descriptive delta; pilot was balanced-stratified and full run is population-based"
        ),
    }


def _report(
    *,
    dataset: Any,
    manifest: PilotManifest,
    population: Mapping[str, Any],
    v3_reference: Mapping[str, Any],
    baseline: Mapping[str, Mapping[str, Any]],
    baseline_provenance: Mapping[str, Any],
    metadata: Mapping[str, object],
    records: Sequence[PilotRunRecord],
    successful_at_start: set[str],
    started_at: str,
    runtime_seconds: float,
    budget: RequestBudget,
    continuity: ModelVersionContinuity,
    stop_reason: str | None,
    first_pending_probe: str | None,
    run_terminal_ids: set[str],
    run_terminal_failures: int,
) -> dict[str, Any]:
    config = _transport_config()
    predictions = _record_predictions(records)
    successful_ids = [
        example_id for example_id in manifest.example_ids if example_id in predictions
    ]
    pending_ids = [
        example_id for example_id in manifest.example_ids if example_id not in predictions
    ]
    ground_truth = {record.example_id: record.human_label for record in manifest.records}
    _, all_metadata, lengths = _examples_and_metadata(dataset, manifest)
    metadata_for_metrics = {
        example_id: {"task_type": value["task_type"], "model": value["model"]}
        for example_id, value in all_metadata.items()
    }
    local_summary = summarize_provider_records(records, ground_truth, metadata_for_metrics)
    baseline_results = _baseline_summaries(baseline, ground_truth, metadata_for_metrics)
    complete = len(successful_ids) == FULL_SIZE and not pending_ids
    local_summary["metric_validity"] = (
        "DECISION_VALID" if complete else "PARTIAL_NON_DECISION_VALID"
    )
    local_summary["provenance"] = {
        **metadata,
        "provider": LOCAL_PROVIDER,
        "gateway": "Ollama local service",
        "base_url_identifier": "127.0.0.1:11434/api/chat",
        "semantic_prompt_version": JUDGE_PROMPT_VERSION,
        "semantic_prompt_hash": JUDGE_PROMPT_SHA256,
        "primary_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "schema_hash": config.schema_hash,
        "output_mode": JudgeOutputMode.JSON_SCHEMA_STRICT,
        "sampling": _sampling().__dict__,
        "transport_version": config.transport_version,
        "transport_hash": config.transport_hash(),
        "transport_prompt_version": CLASSIFICATION_TRANSPORT_VERSION,
        "transport_prompt_hash": CLASSIFICATION_TRANSPORT_PROMPT_SHA256,
        "transport_config": config.canonical_dict(),
        "output_modes_observed": sorted({record.trace.actual_output_mode for record in records}),
        "dataset_revision": EXPECTED_SOURCE_REVISION,
        "pilot_manifest_version": FULL_MANIFEST_ID,
        "source_git_commit": _git_head(),
        "routing_immutable": True,
        "thinking_mode": "OFF",
    }
    report: dict[str, Any] = {
        "schema_version": "phase5b-local-full-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "COMPLETE" if complete else (stop_reason or "INCOMPLETE_LOCAL_TECHNICAL_FAILURE"),
        "classification": "OFFICIAL_RAGTRUTH_FULL_TEST_GOOD_POPULATION",
        "pilot_run_head": _git_head(),
        "source_commit": _git_head(),
        "session_id": f"phase5b-local-full-{datetime.now(UTC):%Y%m%d-%H%M%S}",
        "session_started_at": started_at,
        "session_ended_at": datetime.now(UTC).isoformat(),
        "dataset": {
            **population,
            "benchmark": "ragtruth",
            "split": "test",
            "quality_filter": ["good"],
            "annotation_policy": AnnotationPolicy.STRICT_GROUNDEDNESS.value,
            "source_revision": EXPECTED_SOURCE_REVISION,
            "full_population_target": FULL_SIZE,
        },
        "manifest": {
            "pilot_id": manifest.pilot_id,
            "manifest_version": manifest.manifest_version,
            "sampling_seed": manifest.sampling_seed,
            "sampling_strategy": manifest.sampling_strategy,
            "example_count": len(manifest.example_ids),
            "id_order_sha256": hashlib.sha256("\n".join(manifest.example_ids).encode()).hexdigest(),
        },
        "semantic_prompt_version": JUDGE_PROMPT_VERSION,
        "semantic_prompt_hash": JUDGE_PROMPT_SHA256,
        "primary_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "primary_schema_hash": config.schema_hash,
        "transport_version": CLASSIFICATION_TRANSPORT_VERSION,
        "transport_hash": config.transport_hash(),
        "transport_prompt_version": CLASSIFICATION_TRANSPORT_VERSION,
        "transport_prompt_hash": CLASSIFICATION_TRANSPORT_PROMPT_SHA256,
        "transport_config": config.canonical_dict(),
        "provider": LOCAL_PROVIDER,
        "model": MODEL,
        "local_model_digest": EXPECTED_MODEL_DIGEST,
        "model_version": EXPECTED_MODEL_DIGEST,
        "model_version_check": continuity.status,
        "model_provenance": dict(metadata),
        "v3_reference": dict(v3_reference),
        "baseline_provenance": dict(baseline_provenance),
        "baseline_results": baseline_results,
        "preflight_status": "PASS",
        "leakage_check": "PASS",
        "reasoning_persisted": False,
        "source_text_or_raw_response_persisted": False,
        "successful_at_start": len(successful_at_start),
        "new_valid_success": len(set(successful_ids) - successful_at_start),
        "successful_at_end": len(successful_ids),
        "pending_at_end": len(pending_ids),
        "pending_ids_at_end": pending_ids,
        "successful_ids_at_end": successful_ids,
        "first_pending_probe": first_pending_probe,
        "new_local_requests": budget.requests_used,
        "new_external_requests": 0,
        "rpd_events": 0,
        "rpm_events": 0,
        "tpm_events": 0,
        "terminal_attempted_examples_this_session": len(run_terminal_ids),
        "terminal_failures_this_session": run_terminal_failures,
        "error_counts": dict(
            sorted(
                Counter(
                    record.trace.error_class for record in records if record.trace.error_class
                ).items()
            )
        ),
        "technical_reliability": {
            "total_records": len(records),
            "api_success_count": sum(record.trace.api_success for record in records),
            "parse_success_count": sum(record.trace.parse_success for record in records),
            "valid_success_count": len(predictions),
            "terminal_failure_count": len(records) - len(predictions),
            "retry_record_count": sum(record.attempt > 1 for record in records),
            "validity_rate": len(predictions) / len(records) if records else 0.0,
            "circuit_breaker": {
                "failure_limit": 10,
                "minimum_attempted_examples": 100,
                "minimum_validity_rate": 0.98,
                "status": "NOT_TRIPPED"
                if stop_reason != "FULL_RUN_TECHNICAL_RELIABILITY_REGRESSION"
                else "TRIPPED",
            },
        },
        "local_results": local_summary,
        "decision_validity": "DECISION_VALID" if complete else "PARTIAL_NON_DECISION_VALID",
        "total_runtime_seconds": round(runtime_seconds, 2),
        "performance": _performance_summary(records, runtime_seconds),
        "phase5b_local_status": "COMPLETE" if complete else "INCOMPLETE",
        "push_performed": "NO",
    }
    if not complete:
        report.update(
            {
                "comparisons": {"status": "PARTIAL_NON_DECISION_VALID"},
                "three_evaluator_analysis": {"status": "PARTIAL_NON_DECISION_VALID"},
                "bootstrap": {"status": "PARTIAL_NON_DECISION_VALID"},
                "pilot_vs_full_delta": {"status": "PARTIAL_NON_DECISION_VALID"},
                "next_action": (
                    "Resume the same frozen full local run; do not start another experiment."
                ),
            }
        )
        return report
    full_analysis = summarize_full_predictions(
        ground_truth,
        predictions,
        metadata_for_metrics,
        lengths,
        confidence=_confidence_by_id(records),
    )
    report["local_results"] = {**local_summary, **full_analysis}
    report["task_slices"] = full_analysis["task_slices"]
    report["source_model_slices"] = full_analysis["source_model_slices"]
    report["length_slices"] = full_analysis["length_slices"]
    report["calibration"] = full_analysis["calibration"]
    report["error_analysis"] = full_analysis["error_analysis"]
    report["bootstrap"] = bootstrap_confidence_intervals(
        manifest.example_ids,
        ground_truth,
        predictions,
        baseline["hhem"],
        seed=BOOTSTRAP_SEED,
        replicates=BOOTSTRAP_REPLICATES,
    )
    report["comparisons"] = {
        "status": "DECISION_VALID",
        "local_vs_hhem": compare_pilot_predictions(ground_truth, baseline["hhem"], predictions),
        "local_vs_heuristic": compare_pilot_predictions(
            ground_truth, baseline["heuristic"], predictions
        ),
    }
    report["three_evaluator_analysis"] = build_local_three_evaluator_analysis(
        ground_truth, baseline["heuristic"], baseline["hhem"], predictions
    )
    report["pilot_vs_full_delta"] = _v3_delta(full_analysis["metrics"])
    report["next_action"] = (
        "Review and publish the completed EvalOps Lab benchmark baseline if the full-run "
        "evidence is accepted."
    )
    return report


def _preflight(args: argparse.Namespace) -> dict[str, Any]:
    _assert_clean_source_tree()
    dataset = _load_dataset(args.data_dir)
    population = _validate_population(args.data_dir, dataset)
    v3_reference = _validate_v3_report()
    baseline, baseline_provenance = _validate_baselines(dataset)
    metadata = _verify_model()
    config = _transport_config()
    payload: dict[str, Any] = {
        "schema_version": "phase5b-local-full-preflight-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "PASS",
        "source_git_commit": _git_head(),
        "population": population,
        "v3_reference": v3_reference,
        "baselines": baseline_provenance,
        "model": metadata,
        "semantic_prompt_version": JUDGE_PROMPT_VERSION,
        "semantic_prompt_hash": JUDGE_PROMPT_SHA256,
        "primary_schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "primary_schema_hash": config.schema_hash,
        "transport_version": config.transport_version,
        "transport_hash": config.transport_hash(),
        "transport_config": config.canonical_dict(),
        "external_requests": 0,
        "local_inference_requests": 0,
        "raw_model_response_persisted": False,
        "reasoning_persisted": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(args.preflight_artifact, payload)
    return payload


def _run(args: argparse.Namespace) -> dict[str, Any]:
    _assert_clean_source_tree()
    dataset = _load_dataset(args.data_dir)
    population = _validate_population(args.data_dir, dataset)
    v3_reference = _validate_v3_report()
    baseline, baseline_provenance = _validate_baselines(dataset)
    metadata = _verify_model()
    manifest = _build_manifest(dataset)
    examples, _, _ = _examples_and_metadata(dataset, manifest)
    state = PilotStateStore(args.state)
    _validate_existing_state(state, set(manifest.example_ids))
    existing_records = _state_records(state, manifest.example_ids)
    existing_predictions = _record_predictions(existing_records)
    successful_at_start = set(existing_predictions)
    first_pending_probe = next(
        (
            example_id
            for example_id in manifest.example_ids
            if example_id not in successful_at_start
        ),
        None,
    )
    continuity = ModelVersionContinuity({EXPECTED_MODEL_DIGEST})
    for record in existing_records:
        if record.status == "SUCCESS":
            continuity.observe(record.trace.model_version)
    evaluator = _evaluator(metadata)
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    budget = RequestBudget(None)
    session_terminal_ids: set[str] = set()
    session_failures = 0

    def evaluate_local(context: str, response: str, example_id: str) -> JudgeEvaluationTrace:
        trace = evaluator.evaluate_with_trace(context, response, example_id)
        continuity.observe(trace.model_version)
        return trace

    def observe(record: PilotRunRecord) -> None:
        nonlocal session_failures
        session_terminal_ids.add(record.example_id)
        if record.trace.prediction is None:
            session_failures += 1
        success_count = len(successful_at_start) + sum(
            item.trace.prediction is not None
            for item in _state_records(state, manifest.example_ids)
            if item.example_id not in successful_at_start
        )
        print(
            f"FULL_PROGRESS success={success_count}/{FULL_SIZE} "
            f"example_id={record.example_id} status={record.status}",
            flush=True,
        )
        if session_failures >= 10:
            raise FullRunTechnicalReliabilityRegression("FULL_RUN_TECHNICAL_RELIABILITY_REGRESSION")
        if len(session_terminal_ids) >= 100:
            current_records = _state_records(state, manifest.example_ids)
            valid_count = sum(item.trace.prediction is not None for item in current_records)
            if valid_count / len(session_terminal_ids) < 0.98:
                raise FullRunTechnicalReliabilityRegression(
                    "FULL_RUN_TECHNICAL_RELIABILITY_REGRESSION"
                )

    stop_reason: str | None = None
    try:
        if first_pending_probe is not None:
            print(f"FULL_FIRST_PENDING_PROBE example_id={first_pending_probe}", flush=True)
        run_provider_pilot(
            manifest,
            examples,
            {LOCAL_PROVIDER: evaluate_local},
            state,
            budget,
            max_retries=2,
            parse_regenerations={LOCAL_PROVIDER: 1},
            record_observer=observe,
        )
    except ModelVersionChangedError as error:
        stop_reason = str(error)
    except FullRunTechnicalReliabilityRegression as error:
        stop_reason = str(error)
    records = _state_records(state, manifest.example_ids)
    result = _report(
        dataset=dataset,
        manifest=manifest,
        population=population,
        v3_reference=v3_reference,
        baseline=baseline,
        baseline_provenance=baseline_provenance,
        metadata=metadata,
        records=records,
        successful_at_start=successful_at_start,
        started_at=started_at,
        runtime_seconds=time.perf_counter() - started,
        budget=budget,
        continuity=continuity,
        stop_reason=stop_reason,
        first_pending_probe=first_pending_probe,
        run_terminal_ids=session_terminal_ids,
        run_terminal_failures=session_failures,
    )
    _write_json(args.report, result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the authorized full local Qwen3 RAGTruth benchmark."
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--preflight-artifact", type=Path, default=DEFAULT_PREFLIGHT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = _preflight(args) if args.preflight else _run(args)
        print(
            json.dumps(
                {
                    "STATUS": result["status"],
                    "SUCCESSFUL_AT_END": result.get("successful_at_end", 0),
                    "PENDING_AT_END": result.get("pending_at_end", 0),
                    "LOCAL_INFERENCE_REQUESTS": result.get("new_local_requests", 0),
                },
                ensure_ascii=False,
            )
        )
        return 0 if result["status"] in {"PASS", "COMPLETE"} else 2
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
