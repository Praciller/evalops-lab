"""Bounded Phase 5A Gemini/Groq pilot orchestration.

This script is intentionally explicit about external calls. Importing it has no
network side effects; ``--sample-only`` is offline, and real calls require a
successful synthetic preflight artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.evaluators.judge.evaluator import LLMJudgeEvaluator
from evalops.evaluators.judge.prompt import (
    JUDGE_PROMPT_SHA256,
    JUDGE_PROMPT_VERSION,
    JUDGE_SCHEMA_VERSION,
    render_judge_prompt,
)
from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    JudgeOutputMode,
    OKMDProviderAdapter,
    SamplingConfig,
)
from evalops.models.hallucination import (
    AnnotationPolicy,
    HallucinationLabel,
    HallucinationPrediction,
)
from evalops.pilot.analysis import (
    build_multi_evaluator_analysis,
    compare_pilot_predictions,
    recommend_phase5b_judge,
    summarize_consistency,
    summarize_provider_records,
)
from evalops.pilot.execution import (
    PilotRequestLimitError,
    PilotStateStore,
    RequestBudget,
    run_provider_pilot,
)
from evalops.pilot.models import PilotManifest, PilotRunRecord
from evalops.pilot.provenance import ModelVersionChangedError, ModelVersionContinuity
from evalops.pilot.rate_limit import (
    RateAwareRequestScheduler,
    RateLimitStopError,
)
from evalops.pilot.readiness import assess_llm_judge_readiness
from evalops.pilot.sampling import build_consistency_manifest, build_pilot_manifest
from evalops.providers.okmd import (
    OKMDModel,
    estimate_pilot_tokens,
    model_family,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PROVIDER_NAMES = ("gemini",)
MAX_DAILY_RESUME_REQUESTS = 120
RETRY_HEADROOM_REQUESTS = 10
DEFAULT_RATE_INTERVAL_SECONDS = 10.0
OKMD_MAX_CANDIDATES = 3
OKMD_OUTPUT_MODE = JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION
DEFAULT_MANIFEST = REPO_ROOT / "datasets" / "manifests" / "ragtruth-llm-judge-pilot-v1.json"
DEFAULT_STATE = REPO_ROOT / "reports" / "phase5a-pilot-state.json"
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase5a-pilot-v1.json"
DEFAULT_PREFLIGHT = REPO_ROOT / "reports" / "phase5a-preflight.json"
DEFAULT_DATA_DIR = REPO_ROOT / "datasets" / "external" / "ragtruth"
HEURISTIC_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-heuristic-v1.json"
HHEM_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-hhem-v1.json"
OKMD_DISCOVERY_SNAPSHOT = REPO_ROOT / "reports" / "okmd-model-discovery.json"
EXPECTED_PILOT_STRATUM_COUNTS = {
    f"{task_type}:{label.value}": 20
    for task_type in ("Data2txt", "QA", "Summary")
    for label in (HallucinationLabel.GROUNDED, HallucinationLabel.HALLUCINATED)
}


def estimate_request_count(pilot_size: int, *, include_consistency: bool) -> int:
    """Estimate preflight, base, and optional consistency requests."""

    return 2 + pilot_size + (24 if include_consistency else 0)


def preflight_request_count(previous_external_requests: int) -> int:
    """Add the two synthetic requests used by the single-provider preflight."""

    if previous_external_requests < 0:
        raise ValueError("previous external request count cannot be negative")
    return previous_external_requests + 2


def _resume_request_budget(remaining_pending: int) -> int:
    """Bound one resume window by pending work plus retry headroom."""

    if remaining_pending < 0:
        raise ValueError("remaining pending count cannot be negative")
    return min(remaining_pending + RETRY_HEADROOM_REQUESTS, MAX_DAILY_RESUME_REQUESTS)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_head() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _load_dataset(data_dir: Path):
    preparation = data_dir / "preparation-manifest.json"
    source_revision = "unknown"
    if preparation.is_file():
        payload = json.loads(preparation.read_text(encoding="utf-8"))
        source_revision = str(payload.get("source_revision", source_revision))
    return load_ragtruth_dataset(
        data_dir / "response.jsonl",
        data_dir / "source_info.jsonl",
        split="test",
        source_revision=source_revision,
    )


def _load_or_create_manifest(dataset: Any, path: Path, *, sample_only: bool) -> PilotManifest:
    if path.is_file():
        return PilotManifest.model_validate_json(path.read_text(encoding="utf-8"))
    manifest = build_pilot_manifest(dataset)
    if sample_only:
        _write_json(path, manifest.model_dump(mode="json"))
    return manifest


def _validate_pilot_manifest(manifest: PilotManifest) -> None:
    """Validate the exact frozen population before any provider request."""

    if manifest.pilot_id != "ragtruth-llm-judge-pilot-v1":
        raise ValueError(f"unexpected pilot ID: {manifest.pilot_id}")
    if manifest.split != "test" or manifest.quality_filter != ["good"]:
        raise ValueError("pilot manifest must be frozen to TEST/good examples")
    if manifest.sampling_seed != 20260825:
        raise ValueError(f"unexpected pilot sampling seed: {manifest.sampling_seed}")
    if len(manifest.example_ids) != 120:
        raise ValueError(
            f"pilot manifest must contain 120 examples, found {len(manifest.example_ids)}"
        )
    if manifest.stratum_counts != EXPECTED_PILOT_STRATUM_COUNTS:
        raise ValueError(
            "pilot manifest must contain exactly 20 examples in each of the six frozen strata"
        )
    for record in manifest.records:
        expected_stratum = f"{record.task_type}:{record.human_label.value}"
        if record.stratum != expected_stratum:
            raise ValueError(f"manifest stratum disagrees with human label: {record.example_id}")


def _assert_no_prompt_leakage(
    examples: Mapping[str, tuple[str, str] | object],
) -> None:
    """Require provider inputs to contain only a context/response pair."""

    for example_id, value in examples.items():
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError(
                "prompt leakage guard requires context/response pairs without annotation metadata "
                f"for {example_id}"
            )


def _build_pilot_examples(dataset: Any, manifest: PilotManifest) -> dict[str, tuple[str, str]]:
    """Build judge inputs from source text only and verify manifest alignment."""

    examples_by_id = {example.example_id: example for example in dataset.examples}
    examples: dict[str, tuple[str, str]] = {}
    for record in manifest.records:
        example = examples_by_id.get(record.example_id)
        if example is None:
            raise ValueError(
                f"frozen pilot manifest ID is missing from the TEST dataset: {record.example_id}"
            )
        if example.split != "test" or example.quality != "good":
            raise ValueError(
                f"pilot example is outside the frozen TEST/good population: {record.example_id}"
            )
        if example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS) is not record.human_label:
            raise ValueError(f"pilot human-label mismatch for manifest ID: {record.example_id}")
        examples[record.example_id] = (example.source_context, example.response)
    _assert_no_prompt_leakage(examples)
    return examples


def _partition_resume_ids(
    pilot_ids: Sequence[str],
    *,
    successful_primary_ids: set[str],
    attempted_ids: set[str],
) -> dict[str, list[str]]:
    """Partition the frozen manifest without treating failures as successes."""

    ordered_ids = list(pilot_ids)
    successful = [example_id for example_id in ordered_ids if example_id in successful_primary_ids]
    previous_failed = [
        example_id
        for example_id in ordered_ids
        if example_id in attempted_ids and example_id not in successful_primary_ids
    ]
    never_attempted = [example_id for example_id in ordered_ids if example_id not in attempted_ids]
    pending = [example_id for example_id in ordered_ids if example_id not in successful_primary_ids]
    return {
        "successful_primary_ids": successful,
        "previous_failed_ids": previous_failed,
        "never_attempted_ids": never_attempted,
        "pending_ids": pending,
    }


def _validate_existing_success_config(
    records: Sequence[PilotRunRecord],
) -> None:
    """Refuse to mix historical successes from a different frozen experiment."""

    expected_sampling = {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_output_tokens": 256,
        "reasoning_effort": "low",
        "include_reasoning": False,
    }
    for record in records:
        trace = record.trace
        config = trace.prediction.evaluator_config if trace.prediction is not None else {}
        if (
            record.provider != "gemini"
            or trace.requested_model != "gemini-2.5-flash-lite"
            or not trace.parse_success
            or trace.prediction is None
            or config.get("prompt_version") != JUDGE_PROMPT_VERSION
            or config.get("prompt_sha256") != JUDGE_PROMPT_SHA256
            or config.get("schema_version") != JUDGE_SCHEMA_VERSION
            or config.get("output_mode") != JudgeOutputMode.JSON_SCHEMA_STRICT
            or config.get("sampling") != expected_sampling
        ):
            raise RuntimeError("EXISTING_RESULT_CONFIG_MISMATCH")


def _trace_progress_summary(trace: Any) -> dict[str, Any]:
    """Project a trace to safe progress/provenance fields only."""

    return {
        "api_success": trace.api_success,
        "parse_success": trace.parse_success,
        "structured_output_status": trace.structured_output_status,
        "requested_model": trace.requested_model,
        "model_version": trace.model_version,
        "response_id": trace.response_id,
        "observed_at": trace.observed_at,
        "usage": trace.usage,
        "latency_ms": trace.latency_ms,
        "error_class": trace.error_class,
        "rate_limit_dimension": trace.rate_limit_dimension,
        "retry_after_seconds": trace.retry_after_seconds,
    }


def _sampling() -> SamplingConfig:
    return SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=256,
        reasoning_effort="low",
        include_reasoning=False,
    )


def _provider_evaluators(
    provider_names: Sequence[str] = OFFICIAL_PROVIDER_NAMES,
    output_modes: Mapping[str, str] | None = None,
    okmd_model: Mapping[str, str] | None = None,
) -> dict[str, LLMJudgeEvaluator]:
    environment_names = {
        "gemini": "GEMINI_API_KEY",
        "okmd": "OKMD_API_KEY",
    }
    keys = {
        provider: os.environ.get(environment_names[provider], "").strip()
        for provider in provider_names
    }
    missing = [provider for provider, value in keys.items() if not value]
    if missing:
        raise RuntimeError(
            f"required provider credential environment variable is missing: {','.join(missing)}"
        )
    sampling = _sampling()
    modes = output_modes or {}
    evaluators: dict[str, LLMJudgeEvaluator] = {}
    for provider in provider_names:
        mode = modes.get(provider)
        if provider == "gemini":
            adapter = GeminiProviderAdapter(
                keys[provider], output_mode=mode or JudgeOutputMode.JSON_SCHEMA_STRICT
            )
        elif provider == "okmd":
            if not okmd_model or not okmd_model.get("model_id"):
                raise RuntimeError("OKMD selected model metadata is missing")
            adapter = OKMDProviderAdapter(
                keys[provider],
                model=okmd_model["model_id"],
                catalog_model_name=okmd_model.get("name", "unavailable"),
                output_mode=mode or OKMD_OUTPUT_MODE,
            )
        else:
            raise RuntimeError(f"unsupported Phase 5A provider: {provider}")
        evaluators[provider] = LLMJudgeEvaluator(adapter, sampling=sampling)
    return evaluators


SYNTHETIC_PREFLIGHT_CASES = (
    {
        "example_id": "phase5a-grounded",
        "context": "The source context states that the value is seven.",
        "response": "The value is seven.",
        "expected_label": "GROUNDED",
    },
    {
        "example_id": "phase5a-hallucinated",
        "context": "The source context states that the value is seven.",
        "response": "The value is eight.",
        "expected_label": "HALLUCINATED",
    },
)


def _preflight_case_result(
    evaluator: LLMJudgeEvaluator,
    case: Mapping[str, str],
    *,
    allow_one_regeneration: bool = False,
) -> dict[str, Any]:
    trace = evaluator.evaluate_with_trace(case["context"], case["response"], case["example_id"])
    request_count = 1
    if (
        allow_one_regeneration
        and trace.api_success
        and not trace.parse_success
        and trace.error_class in {"PARSE_ERROR", "SCHEMA_VALIDATION_ERROR"}
    ):
        trace = evaluator.evaluate_with_trace(case["context"], case["response"], case["example_id"])
        request_count = 2
    return {
        "example_id": case["example_id"],
        "expected_label": case["expected_label"],
        "api_success": trace.api_success,
        "parse_success": trace.parse_success,
        "structured_output_status": trace.structured_output_status,
        "label": trace.prediction.label.value if trace.prediction else None,
        "returned_model": trace.returned_model,
        "model_version": trace.model_version,
        "response_id": trace.response_id,
        "observed_at": trace.observed_at,
        "usage": trace.usage,
        "latency_ms": trace.latency_ms,
        "error_class": trace.error_class,
        "rate_limit_dimension": trace.rate_limit_dimension,
        "retry_after_seconds": trace.retry_after_seconds,
        "safe_error_summary": trace.safe_error_summary,
        "requested_output_mode": trace.requested_output_mode,
        "actual_output_mode": trace.actual_output_mode,
        "provider_schema_enforced": trace.provider_schema_enforced,
        "local_schema_validated": trace.local_schema_validated,
        "gateway": trace.gateway,
        "catalog_model_name": trace.catalog_model_name,
        "returned_provider": trace.returned_provider,
        "backend_revision": trace.backend_revision,
        "quota": trace.quota,
        "request_count": request_count,
    }


def _provider_preflight_result(
    evaluator: LLMJudgeEvaluator,
    cases: Sequence[Mapping[str, str]],
    *,
    diagnostics: Mapping[str, Any] | None = None,
    allow_one_regeneration: bool = False,
) -> dict[str, Any]:
    case_results = [
        _preflight_case_result(
            evaluator,
            case,
            allow_one_regeneration=allow_one_regeneration,
        )
        for case in cases
    ]
    return {
        "provider": evaluator.provider.provider_name,
        "provider_family": getattr(
            evaluator.provider,
            "provider_family",
            evaluator.provider.provider_name,
        ),
        "model": evaluator.provider.model,
        "base_url_identifier": evaluator.provider.base_url_identifier,
        "requested_output_mode": evaluator.provider.output_mode,
        "actual_output_mode": (
            case_results[0]["actual_output_mode"]
            if case_results
            else evaluator.provider.output_mode
        ),
        "provider_schema_enforced": evaluator.provider.output_mode
        == JudgeOutputMode.JSON_SCHEMA_STRICT,
        "local_schema_validated": True,
        "model_versions": sorted(
            {
                item["model_version"]
                for item in case_results
                if item.get("model_version") is not None
            }
        ),
        "response_ids": [
            item["response_id"] for item in case_results if item.get("response_id") is not None
        ],
        "api_success_count": sum(item["api_success"] for item in case_results),
        "parse_success_count": sum(item["parse_success"] for item in case_results),
        "cases": case_results,
        "diagnostics": dict(diagnostics or {}),
        "requests_used": sum(item["request_count"] for item in case_results),
    }


def _configuration_hash(evaluator: LLMJudgeEvaluator) -> str:
    serialized = json.dumps(evaluator.config, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _okmd_pilot_estimate(data_dir: Path, manifest_path: Path) -> tuple[PilotManifest, int]:
    dataset = _load_dataset(data_dir)
    manifest = _load_or_create_manifest(dataset, manifest_path, sample_only=False)
    if len(manifest.example_ids) != 120:
        raise RuntimeError(
            f"pilot manifest must contain 120 examples, found {len(manifest.example_ids)}"
        )
    selected_ids = set(manifest.example_ids)
    prompts = [
        render_judge_prompt(example.source_context, example.response)
        for example in dataset.examples
        if example.example_id in selected_ids
    ]
    if len(prompts) != 120:
        raise RuntimeError(
            "frozen pilot manifest is not fully present in the official TEST dataset"
        )
    return manifest, estimate_pilot_tokens(prompts, output_tokens=256, safety_margin=0.25)


def _okmd_candidate_is_non_gemini(candidate: OKMDModel, result: Mapping[str, Any]) -> bool:
    observed = []
    for case in result.get("cases", []):
        for value in (case.get("returned_provider"), case.get("returned_model")):
            if isinstance(value, str) and value:
                observed.append(model_family(value))
    if not observed:
        observed.append(model_family(candidate))
    return all(family != "Gemini" for family in observed)


def _preflight(
    *,
    prior_external_requests: int,
    prior_repair_requests: int,
    data_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    dataset = _load_dataset(data_dir)
    manifest = _load_or_create_manifest(dataset, manifest_path, sample_only=False)
    _validate_pilot_manifest(manifest)
    pilot_examples = _build_pilot_examples(dataset, manifest)
    gemini_evaluator = _provider_evaluators(
        ("gemini",), {"gemini": JudgeOutputMode.JSON_SCHEMA_STRICT}
    )["gemini"]
    gemini_result = _provider_preflight_result(gemini_evaluator, SYNTHETIC_PREFLIGHT_CASES)
    results = {"gemini": gemini_result}
    readiness = assess_llm_judge_readiness(("gemini",), results)
    selected_providers = list(readiness["qualified_providers"])
    output_modes = (
        {"gemini": JudgeOutputMode.JSON_SCHEMA_STRICT} if "gemini" in selected_providers else {}
    )
    config_hashes = {
        provider: _configuration_hash(_provider_evaluators((provider,), output_modes)[provider])
        for provider in selected_providers
    }
    preflight_requests = gemini_result["requests_used"]
    repair_requests = prior_repair_requests + preflight_requests
    pilot_prompts = [
        render_judge_prompt(context, response) for context, response in pilot_examples.values()
    ]
    pilot_token_estimate = estimate_pilot_tokens(
        pilot_prompts,
        output_tokens=256,
        safety_margin=0.25,
    )
    return {
        "schema_version": "phase5a-preflight-v4",
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version_judge": JUDGE_SCHEMA_VERSION,
        "prior_external_requests": prior_external_requests,
        "prior_repair_requests": prior_repair_requests,
        "repair_external_requests": repair_requests,
        "external_requests": prior_external_requests + repair_requests,
        "preflight_requests": preflight_requests,
        "selected_providers": selected_providers,
        "output_modes": output_modes,
        "provider_config_hashes": config_hashes,
        "providers": results,
        "readiness": readiness,
        "llm_judge_ready": readiness["llm_judge_ready"],
        "multi_provider_ready": readiness["multi_provider_ready"],
        "pilot_manifest_validation": "PASS",
        "gemini_pilot_token_estimate": pilot_token_estimate,
        "consistency_plan": {
            "seed": 20260826,
            "per_stratum": 2,
            "requests_per_provider": 24,
        },
        "okmd_benchmark_status": "DEFERRED_RUNTIME_CONTRACT_MISMATCH",
        "multi_provider_deferral": "DEFERRED_SINGLE_PROVIDER_PILOT",
    }


def _prior_preflight_requests(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("external_requests"), int):
        raise RuntimeError("existing preflight artifact has no valid request ledger")
    previous = int(payload.get("prior_external_requests", payload["external_requests"]))
    if previous < 0 or previous > 300:
        raise RuntimeError("existing preflight artifact has an invalid request ledger")
    return previous


def _prior_repair_requests(path: Path) -> int:
    values: list[int] = []
    ledger = path.with_name("phase5a-repair-ledger.json")
    if ledger.is_file():
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        value = payload.get("repair_external_requests", 0) if isinstance(payload, dict) else 0
        if isinstance(value, int) and 0 <= value <= 300:
            values.append(value)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("repair_external_requests", 0) if isinstance(payload, dict) else 0
        if isinstance(value, int) and 0 <= value <= 300:
            values.append(value)
    return max(values, default=0)


def _validate_preflight(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected_providers = payload.get("selected_providers") if isinstance(payload, dict) else None
    readiness = payload.get("readiness") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("external_requests"), int)
        or not isinstance(payload.get("repair_external_requests"), int)
        or payload.get("repair_external_requests") < 0
        or payload.get("repair_external_requests") > 300
        or not isinstance(selected_providers, list)
        or not selected_providers
        or len(selected_providers) != len(set(selected_providers))
        or not isinstance(readiness, dict)
        or readiness.get("llm_judge_ready") is not True
        or readiness.get("qualified_providers") != selected_providers
    ):
        raise RuntimeError("preflight artifact is missing a valid LLM judge readiness gate")
    for provider in selected_providers:
        result = payload.get("providers", {}).get(provider, {})
        api_success_count = result.get("api_success_count")
        parse_success_count = result.get("parse_success_count")
        if (
            not isinstance(api_success_count, int)
            or not isinstance(parse_success_count, int)
            or api_success_count <= 0
            or api_success_count != parse_success_count
        ):
            raise RuntimeError(f"PROVIDER_PREFLIGHT_BLOCKED={provider}")
    return payload


def _artifact_predictions(path: Path, expected_ids: set[str]) -> dict[str, HallucinationPrediction]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    per_example = payload.get("details", {}).get("per_example", {})
    if not isinstance(per_example, dict) or not expected_ids.issubset(per_example):
        raise ValueError(f"baseline artifact does not contain every pilot ID: {path.name}")
    predictions: dict[str, HallucinationPrediction] = {}
    for example_id in sorted(expected_ids):
        record = per_example[example_id]
        predictions[example_id] = HallucinationPrediction(
            example_id=example_id,
            label=HallucinationLabel(record["predicted_label"]),
            score=float(record.get("score", 0.0)),
            support_score=record.get("support_score"),
            evaluator_name=str(
                payload.get("details", {}).get("evaluator", {}).get("name", "baseline")
            ),
        )
    return predictions


def _baseline_summary(
    name: str,
    predictions: Mapping[str, HallucinationPrediction],
    ground_truth: Mapping[str, HallucinationLabel],
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    report = evaluate_hallucination_predictions(
        ground_truth, list(predictions.values()), metadata=metadata
    )
    return {
        "evaluator": name,
        "example_count": len(predictions),
        "confusion_matrix": report.confusion_matrix.model_dump(mode="json"),
        "metrics": report.metrics,
        "task_slices": report.slices.get("task_type", {}),
    }


def _provider_provenance(
    evaluator: LLMJudgeEvaluator,
    records: Sequence[PilotRunRecord],
    manifest: PilotManifest,
) -> dict[str, Any]:
    returned_models = sorted(
        {
            record.trace.returned_model
            for record in records
            if record.trace.returned_model is not None
        }
    )
    returned_providers = sorted(
        {
            record.trace.returned_provider
            for record in records
            if record.trace.returned_provider is not None
        }
    )
    model_versions = sorted(
        {record.trace.model_version for record in records if record.trace.model_version is not None}
    )
    response_ids = [
        record.trace.response_id for record in records if record.trace.response_id is not None
    ]
    observed_at = [
        record.trace.observed_at for record in records if record.trace.observed_at is not None
    ]
    quotas = [record.trace.quota for record in records if record.trace.quota is not None]
    return {
        "provider": evaluator.provider.provider_name,
        "gateway": getattr(evaluator.provider, "gateway", None),
        "base_url_identifier": evaluator.provider.base_url_identifier,
        "requested_model": evaluator.provider.model,
        "catalog_model_name": getattr(evaluator.provider, "catalog_model_name", None),
        "returned_models": returned_models,
        "model_versions": model_versions,
        "response_ids": response_ids,
        "observed_at": observed_at,
        "returned_providers": returned_providers,
        "backend_revision": getattr(evaluator.provider, "backend_revision", "unavailable"),
        "model_revision": getattr(evaluator.provider, "backend_revision", "unavailable"),
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version": JUDGE_SCHEMA_VERSION,
        "output_mode": evaluator.config["output_mode"],
        "routing_immutable": getattr(evaluator.provider, "routing_immutable", None),
        "latest_quota": quotas[-1] if quotas else None,
        "sampling": evaluator.config["sampling"],
        "dataset_revision": manifest.dataset_revision,
        "pilot_manifest_version": manifest.manifest_version,
        "git_commit": _git_head(),
    }


def _record_map(records: Sequence[PilotRunRecord]) -> dict[str, HallucinationPrediction]:
    return {
        record.example_id: record.trace.prediction
        for record in records
        if record.trace.prediction is not None
    }


def _records_for_ids(
    state: PilotStateStore,
    provider: str,
    example_ids: Sequence[str],
) -> list[PilotRunRecord]:
    """Read one latest safe state record per frozen manifest ID."""

    return [
        record
        for example_id in example_ids
        if (record := state.get(provider, example_id)) is not None
    ]


def _error_counts(records: Sequence[PilotRunRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.trace.error_class is not None:
            counts[record.trace.error_class] = counts.get(record.trace.error_class, 0) + 1
    return dict(sorted(counts.items()))


def _load_existing_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("existing pilot report must be a JSON object")
    return payload


def _resume_health_check_required(
    pending_ids: Sequence[str],
    prior_health_check: Mapping[str, Any] | None = None,
) -> bool:
    """Disable synthetic health checks; the first pending ID is the probe."""

    del pending_ids
    del prior_health_check
    return False


def _resume_model_version_sets(
    existing_report: Mapping[str, Any],
    successful_model_versions: set[str],
) -> tuple[set[str], set[str]]:
    """Preserve the report's historical/resumed model-version boundary."""

    provenance = existing_report.get("model_version_provenance")
    if isinstance(provenance, dict) and "historical_model_versions" in provenance:
        historical = {
            value
            for value in provenance.get("historical_model_versions", [])
            if isinstance(value, str) and value
        }
        resumed = {
            value
            for value in provenance.get("resumed_model_versions", [])
            if isinstance(value, str) and value
        }
        return historical, resumed
    return set(successful_model_versions), set()


def _validate_frozen_resume_config(preflight: Mapping[str, Any]) -> None:
    if preflight.get("selected_providers") != ["gemini"]:
        raise RuntimeError("FROZEN_PROVIDER_SCOPE_MISMATCH")
    if preflight.get("prompt_version") != JUDGE_PROMPT_VERSION:
        raise RuntimeError("FROZEN_PROMPT_VERSION_MISMATCH")
    if preflight.get("prompt_sha256") != JUDGE_PROMPT_SHA256:
        raise RuntimeError("FROZEN_PROMPT_HASH_MISMATCH")
    if preflight.get("schema_version_judge") != JUDGE_SCHEMA_VERSION:
        raise RuntimeError("FROZEN_SCHEMA_VERSION_MISMATCH")
    if preflight.get("output_modes", {}).get("gemini") != JudgeOutputMode.JSON_SCHEMA_STRICT:
        raise RuntimeError("FROZEN_OUTPUT_MODE_MISMATCH")


def _scheduler_report(
    scheduler: RateAwareRequestScheduler,
    *,
    stop_reason: str | None,
) -> dict[str, Any]:
    dimensions = list(dict.fromkeys(scheduler.rate_limit_dimensions))
    return {
        "min_interval_seconds": scheduler.min_interval_seconds,
        "max_consecutive_rate_limits": scheduler.max_consecutive_rate_limits,
        "rate_limit_count": scheduler.rate_limit_count,
        "rate_limit_dimensions": dimensions,
        "consecutive_rate_limits_at_stop": scheduler.consecutive_rate_limits,
        "circuit_breaker": (
            "TRIPPED"
            if stop_reason
            in {
                "RATE_LIMIT_STILL_BLOCKING",
                "DAILY_QUOTA_EXHAUSTED",
                "DAILY_QUOTA_NOT_RESET",
            }
            else "NOT_TRIPPED"
        ),
    }


def _run_base(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _validate_preflight(args.preflight_artifact)
    _validate_frozen_resume_config(preflight)
    selected_providers = tuple(preflight["selected_providers"])
    existing_report = _load_existing_report(args.report)
    dataset = _load_dataset(args.data_dir)
    manifest = _load_or_create_manifest(dataset, args.manifest, sample_only=False)
    _validate_pilot_manifest(manifest)
    examples = _build_pilot_examples(dataset, manifest)
    expected_ids = set(manifest.example_ids)
    ground_truth = {record.example_id: record.human_label for record in manifest.records}
    metadata = {record.example_id: {"task_type": record.task_type} for record in manifest.records}
    baseline_predictions = {
        "heuristic": _artifact_predictions(HEURISTIC_ARTIFACT, expected_ids),
        "hhem": _artifact_predictions(HHEM_ARTIFACT, expected_ids),
    }
    baseline_id_match = {
        name: set(values) == expected_ids for name, values in baseline_predictions.items()
    }
    if not all(baseline_id_match.values()):
        raise RuntimeError("baseline ID alignment failed before external provider execution")
    evaluators = _provider_evaluators(
        selected_providers,
        preflight["output_modes"],
        preflight.get("okmd_selection"),
    )
    state = PilotStateStore(args.state)
    start_records = {
        provider: _records_for_ids(state, provider, manifest.example_ids)
        for provider in selected_providers
    }
    existing_successes = [
        record
        for records_for_provider in start_records.values()
        for record in records_for_provider
        if record.status == "SUCCESS"
    ]
    _validate_existing_success_config(existing_successes)
    successful_ids = {
        record.example_id for record in existing_successes if record.provider == "gemini"
    }
    attempted_ids = {record.example_id for record in start_records["gemini"]}
    resume_partition = _partition_resume_ids(
        manifest.example_ids,
        successful_primary_ids=successful_ids,
        attempted_ids=attempted_ids,
    )
    resume_base_lifetime_requests = existing_report.get(
        "resume_prior_external_requests",
        existing_report.get("external_requests", preflight["external_requests"]),
    )
    lifetime_requests_at_start = existing_report.get(
        "external_requests", resume_base_lifetime_requests
    )
    cumulative_resume_requests = existing_report.get(
        "resume_new_external_requests",
        max(lifetime_requests_at_start - resume_base_lifetime_requests, 0),
    )
    if (
        not isinstance(resume_base_lifetime_requests, int)
        or resume_base_lifetime_requests < 0
        or not isinstance(lifetime_requests_at_start, int)
        or lifetime_requests_at_start < resume_base_lifetime_requests
        or not isinstance(cumulative_resume_requests, int)
        or cumulative_resume_requests < 0
    ):
        raise RuntimeError("INVALID_RESUME_REQUEST_LEDGER")
    session_started_at = datetime.now(UTC)
    session_id = f"phase5a-resume-{session_started_at:%Y%m%d-%H%M%S}"
    session_request_budget = _resume_request_budget(len(resume_partition["pending_ids"]))
    budget = RequestBudget(session_request_budget)
    scheduler = RateAwareRequestScheduler(min_interval_seconds=DEFAULT_RATE_INTERVAL_SECONDS)
    successful_model_versions = {
        record.trace.model_version
        for record in existing_successes
        if record.trace.model_version is not None
    }
    historical_versions, existing_resumed_versions = _resume_model_version_sets(
        existing_report, successful_model_versions
    )
    continuity = ModelVersionContinuity(historical_versions)
    continuity.resumed_versions.update(existing_resumed_versions)
    stop_reason: str | None = None
    health_result = {
        "attempted": False,
        "status": "NOT_RUN_FIRST_PENDING_PROBE",
    }
    if stop_reason is None:
        try:
            run_provider_pilot(
                manifest,
                examples,
                {name: evaluator.evaluate_with_trace for name, evaluator in evaluators.items()},
                state,
                budget,
                scheduler=scheduler,
                success_observer=lambda record: continuity.observe(record.trace.model_version),
            )
        except (ModelVersionChangedError, RateLimitStopError, PilotRequestLimitError) as error:
            stop_reason = str(error)
    provider_records = {
        provider: _records_for_ids(state, provider, manifest.example_ids)
        for provider in selected_providers
    }
    provider_summaries = {
        provider: {
            **summarize_provider_records(provider_records[provider], ground_truth, metadata),
            "provenance": _provider_provenance(
                evaluators[provider], provider_records[provider], manifest
            ),
        }
        for provider in selected_providers
    }
    provider_predictions = {
        provider: _record_map(provider_records[provider]) for provider in selected_providers
    }
    successful_ids_at_end = [
        example_id
        for example_id in manifest.example_ids
        if example_id in provider_predictions["gemini"]
    ]
    successful_ids_at_start = set(resume_partition["successful_primary_ids"])
    new_valid_ids = [
        example_id
        for example_id in successful_ids_at_end
        if example_id not in successful_ids_at_start
    ]
    pending_ids_at_end = [
        example_id for example_id in manifest.example_ids if example_id not in successful_ids_at_end
    ]
    first_pending_id = (
        resume_partition["pending_ids"][0] if resume_partition["pending_ids"] else None
    )
    first_pending_record = (
        state.get("gemini", first_pending_id) if first_pending_id is not None else None
    )
    first_pending_probe: dict[str, Any] = {
        "example_id": first_pending_id,
        "status": "NOT_REQUIRED_PRIMARY_COMPLETE" if first_pending_id is None else "NOT_OBSERVED",
    }
    if first_pending_record is not None:
        first_pending_probe = {
            "example_id": first_pending_record.example_id,
            "status": first_pending_record.status,
            **_trace_progress_summary(first_pending_record.trace),
        }
    id_match = {
        name: set(values) == expected_ids
        for name, values in {**baseline_predictions, **provider_predictions}.items()
    }
    comparisons: dict[str, Any] = {}
    if all(id_match.values()):
        for provider in selected_providers:
            comparisons[f"{provider}_vs_hhem"] = compare_pilot_predictions(
                ground_truth, baseline_predictions["hhem"], provider_predictions[provider]
            )
            comparisons[f"{provider}_vs_heuristic"] = compare_pilot_predictions(
                ground_truth, baseline_predictions["heuristic"], provider_predictions[provider]
            )
        for left, right in combinations(selected_providers, 2):
            comparisons[f"{left}_vs_{right}"] = compare_pilot_predictions(
                ground_truth, provider_predictions[left], provider_predictions[right]
            )
    else:
        comparisons["status"] = "SKIPPED_ID_MISMATCH"
    complete_predictions = {**baseline_predictions, **provider_predictions}
    multi = (
        build_multi_evaluator_analysis(ground_truth, complete_predictions)
        if all(id_match.values())
        else {"status": "SKIPPED_ID_MISMATCH"}
    )
    primary_complete = all(id_match.values())
    session_ended_at = datetime.now(UTC)
    legacy_repair_requests = existing_report.get(
        "repair_external_requests", preflight["repair_external_requests"]
    )
    if not isinstance(legacy_repair_requests, int):
        legacy_repair_requests = preflight["repair_external_requests"]
    report = {
        "schema_version": "phase5a-pilot-v1",
        "classification": "BALANCED_STRATIFIED_PILOT"
        if primary_complete
        else "COMPLETE_WITH_LIMITATIONS",
        "status": "COMPLETE" if primary_complete else (stop_reason or "PRIMARY_INCOMPLETE"),
        "pilot_name": manifest.pilot_id,
        "pilot_size": len(manifest.example_ids),
        "pilot_seed": manifest.sampling_seed,
        "pilot_strata": manifest.stratum_counts,
        "dataset_revision": manifest.dataset_revision,
        "annotation_policy": AnnotationPolicy.STRICT_GROUNDEDNESS.value,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "judge_schema_version": JUDGE_SCHEMA_VERSION,
        "selected_providers": list(selected_providers),
        "secondary_provider": None,
        "output_modes": preflight["output_modes"],
        "provider_config_hashes": preflight["provider_config_hashes"],
        "git_commit": _git_head(),
        "id_match_check": id_match,
        "pilot_id_match": all(id_match.values()),
        "leakage_check": "PASS",
        "llm_judge_ready": preflight["llm_judge_ready"],
        "multi_provider_ready": preflight["multi_provider_ready"],
        "provider_readiness": preflight["readiness"],
        "multi_provider_deferral": preflight["multi_provider_deferral"],
        "providers": provider_summaries,
        "heuristic_pilot_results": _baseline_summary(
            "heuristic-baseline", baseline_predictions["heuristic"], ground_truth, metadata
        ),
        "hhem_pilot_results": _baseline_summary(
            "hhem-2.1-open", baseline_predictions["hhem"], ground_truth, metadata
        ),
        "comparisons": comparisons,
        "multi_evaluator_analysis": multi,
        "phase5b_recommendation": recommend_phase5b_judge(provider_summaries),
        "phase5b_status": "REVIEW_ONLY"
        if primary_complete
        else "NOT_AUTHORIZED_PRIMARY_INCOMPLETE",
        "prior_external_requests": preflight["prior_external_requests"],
        "repair_external_requests": legacy_repair_requests + budget.requests_used,
        "resume_prior_external_requests": resume_base_lifetime_requests,
        "resume_new_external_requests": cumulative_resume_requests + budget.requests_used,
        "session_new_external_requests": budget.requests_used,
        "fresh_request_budget": session_request_budget,
        "external_requests": lifetime_requests_at_start + budget.requests_used,
        "request_ledger": {
            "prior_lifetime_requests": lifetime_requests_at_start,
            "resume_base_lifetime_requests": resume_base_lifetime_requests,
            "cumulative_resume_requests": cumulative_resume_requests + budget.requests_used,
            "new_requests_used": budget.requests_used,
            "fresh_budget": session_request_budget,
            "remaining_new_requests": session_request_budget - budget.requests_used,
        },
        "quota_status": (
            "DAILY_QUOTA_NOT_RESET"
            if stop_reason == "DAILY_QUOTA_NOT_RESET"
            else "DAILY_QUOTA_EXHAUSTED"
            if stop_reason == "DAILY_QUOTA_EXHAUSTED"
            else "RATE_LIMIT_STILL_BLOCKING"
            if stop_reason == "RATE_LIMIT_STILL_BLOCKING"
            else "FRESH_REQUEST_BUDGET_EXHAUSTED"
            if stop_reason and stop_reason.startswith("Phase 5A request ceiling")
            else "AVAILABLE_WITHIN_SESSION_BUDGET"
        ),
        "metric_validity": "DECISION_VALID" if primary_complete else "PARTIAL_NON_DECISION_VALID",
        "cost_status": "PROVIDER_REPORTED_ONLY",
        "consistency_run": "NOT_RUN" if primary_complete else "NOT_RUN_PRIMARY_INCOMPLETE",
        "consistency": {
            "status": "NOT_RUN" if primary_complete else "NOT_RUN_PRIMARY_INCOMPLETE",
            "reason": (
                "Primary pilot is complete; consistency is a separate optional run."
                if primary_complete
                else "Primary pilot lacks a complete ID-aligned prediction population."
            ),
        },
        "resume_source_commit": _git_head(),
        "pilot_run_head": _git_head(),
        "initial_head": existing_report.get("initial_head", existing_report.get("git_commit")),
        "resume_partition_at_start": resume_partition,
        "existing_successful_at_start": len(resume_partition["successful_primary_ids"]),
        "previously_failed_at_start": len(resume_partition["previous_failed_ids"]),
        "never_attempted_at_start": len(resume_partition["never_attempted_ids"]),
        "pending_at_start": len(resume_partition["pending_ids"]),
        "pending_ids_at_start": resume_partition["pending_ids"],
        "attempted_records_at_end": len(provider_records["gemini"]),
        "completed_valid": len(provider_predictions["gemini"]),
        "successful_ids_at_end": successful_ids_at_end,
        "pending_ids_at_end": pending_ids_at_end,
        "new_valid_results": new_valid_ids,
        "first_pending_probe": first_pending_probe,
        "resume_session": {
            "session_id": session_id,
            "started_at": session_started_at.isoformat(),
            "ended_at": session_ended_at.isoformat(),
            "successful_ids_at_start": resume_partition["successful_primary_ids"],
            "pending_ids_at_start": resume_partition["pending_ids"],
            "new_valid_results": new_valid_ids,
            "successful_ids_at_end": successful_ids_at_end,
            "pending_ids_at_end": pending_ids_at_end,
            "new_external_requests": budget.requests_used,
            "request_budget": session_request_budget,
            "rpd_stop": stop_reason == "DAILY_QUOTA_EXHAUSTED",
            "first_pending_probe": first_pending_probe,
        },
        "resume_health_check": health_result,
        "resume_start_error_counts": {
            provider: _error_counts(records_for_provider)
            for provider, records_for_provider in start_records.items()
        },
        "final_error_counts": {
            provider: _error_counts(records_for_provider)
            for provider, records_for_provider in provider_records.items()
        },
        "rate_limit_policy": {
            "min_interval_seconds": DEFAULT_RATE_INTERVAL_SECONDS,
            "max_consecutive_rate_limits": 3,
            "retry_after_floor": "max(provider_retry_after, 10 seconds)",
            "daily_quota_action": "stop_immediately",
        },
        "rate_limit_diagnostics": _scheduler_report(scheduler, stop_reason=stop_reason),
        "model_version_provenance": {
            "historical_model_versions": sorted(historical_versions),
            "historical_status": continuity.historical_status,
            "resumed_model_versions": sorted(continuity.resumed_versions),
            "continuity_status": continuity.status,
            "first_five_historical_model_version_status": (
                "PASS" if historical_versions else "UNVERIFIED"
            ),
        },
        "frozen_configuration": {
            "provider": "gemini",
            "model": "gemini-2.5-flash-lite",
            "api": "native REST generateContent",
            "output_mode": JudgeOutputMode.JSON_SCHEMA_STRICT,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "prompt_sha256": JUDGE_PROMPT_SHA256,
            "schema_version": JUDGE_SCHEMA_VERSION,
            "annotation_policy": AnnotationPolicy.STRICT_GROUNDEDNESS.value,
            "sampling": _sampling().__dict__,
        },
    }
    _write_json(args.report, report)
    return report


def _run_consistency(args: argparse.Namespace) -> dict[str, Any]:
    report = _load_existing_report(args.report)
    selected_providers = tuple(report.get("selected_providers", ()))
    if not selected_providers:
        raise RuntimeError("consistency requires a completed LLM judge pilot")
    if report.get("pilot_id_match") is not True:
        report["consistency_run"] = "PRIMARY_INCOMPLETE"
        report["consistency"] = {
            "status": "PRIMARY_INCOMPLETE",
            "reason": "Primary pilot predictions are not complete and ID-aligned.",
        }
        _write_json(args.report, report)
        return report
    rate_diagnostics = report.get("rate_limit_diagnostics", {})
    if isinstance(rate_diagnostics, dict) and (
        int(rate_diagnostics.get("rate_limit_count", 0)) > 0
        or bool(rate_diagnostics.get("rate_limit_dimensions"))
    ):
        report["consistency_run"] = "RATE_LIMIT_PRESSURE"
        report["consistency"] = {
            "status": "RATE_LIMIT_PRESSURE",
            "reason": "Consistency is deferred after observed Gemini rate-limit pressure.",
        }
        _write_json(args.report, report)
        return report
    manifest = PilotManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    _validate_pilot_manifest(manifest)
    consistency = build_consistency_manifest(manifest)
    consistency_requests = 24 * len(selected_providers)
    if consistency_requests > MAX_DAILY_RESUME_REQUESTS:
        report["consistency_run"] = "QUOTA_BLOCKED"
        report["consistency"] = {
            "status": "QUOTA_BLOCKED",
            "reason": "The daily Phase 5A request budget cannot fit 24 repeat calls.",
        }
        _write_json(args.report, report)
        return report
    dataset = _load_dataset(args.data_dir)
    dataset_examples = {example.example_id: example for example in dataset.examples}
    examples = {
        record.example_id: (
            dataset_examples[record.example_id].source_context,
            dataset_examples[record.example_id].response,
        )
        for record in consistency.records
        if record.example_id in dataset_examples
    }
    _assert_no_prompt_leakage(examples)
    evaluators = _provider_evaluators(
        selected_providers,
        report.get("output_modes", {}),
        report.get("okmd_selection"),
    )
    budget = RequestBudget(consistency_requests)
    scheduler = RateAwareRequestScheduler(min_interval_seconds=DEFAULT_RATE_INTERVAL_SECONDS)
    repeated: dict[str, list[PilotRunRecord]] = {provider: [] for provider in selected_providers}
    stop_reason: str | None = None
    for repeat in (1, 2):
        repeat_state = PilotStateStore(
            args.report.with_name(f"phase5a-consistency-repeat-{repeat}-state.json")
        )
        try:
            repeat_records = run_provider_pilot(
                consistency,
                examples,
                {name: evaluator.evaluate_with_trace for name, evaluator in evaluators.items()},
                repeat_state,
                budget,
                max_retries=0,
                scheduler=scheduler,
            )
        except (RateLimitStopError, PilotRequestLimitError) as error:
            stop_reason = str(error)
            break
        for record in repeat_records:
            repeated[record.provider].append(record)
    if stop_reason is not None:
        report["consistency_run"] = (
            "QUOTA_BLOCKED"
            if stop_reason.startswith("Phase 5A request ceiling")
            else "RATE_LIMIT_PRESSURE"
        )
        report["consistency"] = {
            "status": report["consistency_run"],
            "reason": stop_reason,
        }
        report["consistency_new_external_requests"] = budget.requests_used
        report["external_requests"] = report.get("external_requests", 0) + budget.requests_used
        report["request_ledger"] = {
            "prior_lifetime_requests": report.get("external_requests", 0) - budget.requests_used,
            "new_requests_used": budget.requests_used,
            "fresh_budget": consistency_requests,
            "remaining_new_requests": consistency_requests - budget.requests_used,
        }
        report["consistency_rate_limit_diagnostics"] = _scheduler_report(
            scheduler, stop_reason=stop_reason
        )
        _write_json(args.report, report)
        return report
    base_state = PilotStateStore(args.state)
    consistency_reports: dict[str, Any] = {}
    for provider in selected_providers:
        records: list[PilotRunRecord] = []
        for record in consistency.records:
            primary = base_state.get(provider, record.example_id)
            if primary is not None:
                records.append(primary)
        records.extend(repeated[provider])
        consistency_reports[provider] = summarize_consistency(records)
    report["consistency_subset"] = {
        "size": len(consistency.example_ids),
        "seed": consistency.sampling_seed,
        "strata": consistency.stratum_counts,
    }
    report["consistency"] = consistency_reports
    report["consistency_run"] = "COMPLETE"
    report["consistency_new_external_requests"] = budget.requests_used
    report["external_requests"] = report.get("external_requests", 0) + budget.requests_used
    report["repair_external_requests"] = report.get("repair_external_requests", 0) + (
        budget.requests_used
    )
    report["request_ledger"] = {
        "prior_lifetime_requests": report.get("external_requests", 0) - budget.requests_used,
        "new_requests_used": budget.requests_used,
        "fresh_budget": consistency_requests,
        "remaining_new_requests": consistency_requests - budget.requests_used,
    }
    report["consistency_rate_limit_diagnostics"] = _scheduler_report(scheduler, stop_reason=None)
    _write_json(args.report, report)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded Phase 5A LLM judge pilot.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--sample-only", action="store_true")
    modes.add_argument("--preflight", dest="preflight_mode", action="store_true")
    modes.add_argument("--run", action="store_true")
    modes.add_argument("--consistency", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--preflight-artifact",
        dest="preflight_artifact",
        type=Path,
        default=DEFAULT_PREFLIGHT,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.sample_only:
        dataset = _load_dataset(args.data_dir)
        manifest = build_pilot_manifest(dataset)
        _write_json(args.manifest, manifest.model_dump(mode="json"))
        print(
            json.dumps({"pilot_size": len(manifest.example_ids), "strata": manifest.stratum_counts})
        )
        return 0
    if args.preflight_mode:
        prior_external_requests = _prior_preflight_requests(args.preflight_artifact)
        prior_repair_requests = _prior_repair_requests(args.preflight_artifact)
        if prior_repair_requests >= 300:
            print(json.dumps({"error": "repair request budget is already exhausted"}))
            return 2
        payload = _preflight(
            prior_external_requests=prior_external_requests,
            prior_repair_requests=prior_repair_requests,
            data_dir=args.data_dir,
            manifest_path=args.manifest,
        )
        _write_json(args.preflight_artifact, payload)
        print(
            json.dumps(
                {
                    "prior_external_requests": payload["prior_external_requests"],
                    "repair_external_requests": payload["repair_external_requests"],
                    "external_requests": payload["external_requests"],
                    "selected_providers": payload["selected_providers"],
                    "providers": payload["providers"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if payload.get("llm_judge_ready") is True else 2
    try:
        report = _run_consistency(args) if args.consistency else _run_base(args)
    except (OSError, ValueError, RuntimeError, PilotRequestLimitError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "phase5a": report.get("classification", "CONSISTENCY"),
                "external_requests": report.get("external_requests"),
                "consistency_run": report.get("consistency_run"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
