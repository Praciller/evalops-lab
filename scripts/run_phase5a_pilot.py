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
from pathlib import Path
from typing import Any

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.hallucination.metrics import evaluate_hallucination_predictions
from evalops.evaluators.judge.evaluator import LLMJudgeEvaluator
from evalops.evaluators.judge.prompt import (
    JUDGE_PROMPT_SHA256,
    JUDGE_PROMPT_VERSION,
    JUDGE_SCHEMA_VERSION,
)
from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
    JudgeOutputMode,
    OpenRouterProviderAdapter,
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
from evalops.pilot.sampling import build_consistency_manifest, build_pilot_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PROVIDER_NAMES = ("gemini", "groq")
OPENROUTER_FALLBACK_NAME = "openrouter"
OPENROUTER_FALLBACK_MODEL = "liquid/lfm-2.5-2.6b:free"
DEFAULT_MANIFEST = REPO_ROOT / "datasets" / "manifests" / "ragtruth-llm-judge-pilot-v1.json"
DEFAULT_STATE = REPO_ROOT / "reports" / "phase5a-pilot-state.json"
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase5a-pilot-v1.json"
DEFAULT_PREFLIGHT = REPO_ROOT / "reports" / "phase5a-preflight.json"
DEFAULT_DATA_DIR = REPO_ROOT / "datasets" / "external" / "ragtruth"
HEURISTIC_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-heuristic-v1.json"
HHEM_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-hhem-v1.json"


def estimate_request_count(pilot_size: int, *, include_consistency: bool) -> int:
    """Estimate preflight, base, and optional consistency requests."""

    return 4 + (2 * pilot_size) + (48 if include_consistency else 0)


def preflight_request_count(previous_external_requests: int) -> int:
    """Add the four required synthetic provider calls to a repair budget."""

    if previous_external_requests < 0:
        raise ValueError("previous external request count cannot be negative")
    return previous_external_requests + 4


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
) -> dict[str, LLMJudgeEvaluator]:
    environment_names = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        OPENROUTER_FALLBACK_NAME: "OPENROUTER_API_KEY",
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
        elif provider == "groq":
            adapter = GroqProviderAdapter(
                keys[provider], output_mode=mode or JudgeOutputMode.JSON_SCHEMA_STRICT
            )
        elif provider == OPENROUTER_FALLBACK_NAME:
            adapter = OpenRouterProviderAdapter(
                keys[provider],
                model=OPENROUTER_FALLBACK_MODEL,
                output_mode=mode or JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION,
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


def _preflight_case_result(evaluator: LLMJudgeEvaluator, case: Mapping[str, str]) -> dict[str, Any]:
    trace = evaluator.evaluate_with_trace(case["context"], case["response"], case["example_id"])
    return {
        "example_id": case["example_id"],
        "expected_label": case["expected_label"],
        "api_success": trace.api_success,
        "parse_success": trace.parse_success,
        "structured_output_status": trace.structured_output_status,
        "label": trace.prediction.label.value if trace.prediction else None,
        "returned_model": trace.returned_model,
        "usage": trace.usage,
        "latency_ms": trace.latency_ms,
        "error_class": trace.error_class,
        "safe_error_summary": trace.safe_error_summary,
        "requested_output_mode": trace.requested_output_mode,
        "actual_output_mode": trace.actual_output_mode,
        "provider_schema_enforced": trace.provider_schema_enforced,
        "local_schema_validated": trace.local_schema_validated,
    }


def _provider_preflight_result(
    evaluator: LLMJudgeEvaluator,
    cases: Sequence[Mapping[str, str]],
    *,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    case_results = [_preflight_case_result(evaluator, case) for case in cases]
    return {
        "provider": evaluator.provider.provider_name,
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
        "api_success_count": sum(item["api_success"] for item in case_results),
        "parse_success_count": sum(item["parse_success"] for item in case_results),
        "cases": case_results,
        "diagnostics": dict(diagnostics or {}),
    }


def _groq_diagnostics() -> tuple[dict[str, Any], int, str | None]:
    basic_evaluator = _provider_evaluators(
        ("groq",), {"groq": JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION}
    )["groq"]
    basic = _preflight_case_result(basic_evaluator, SYNTHETIC_PREFLIGHT_CASES[0])
    diagnostics: dict[str, Any] = {"basic_completion": basic}
    request_count = 1
    if not basic["api_success"]:
        return diagnostics, request_count, None

    object_evaluator = _provider_evaluators(
        ("groq",), {"groq": JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION}
    )["groq"]
    object_result = _preflight_case_result(object_evaluator, SYNTHETIC_PREFLIGHT_CASES[0])
    diagnostics["json_object"] = object_result
    request_count += 1

    strict_evaluator = _provider_evaluators(
        ("groq",), {"groq": JudgeOutputMode.JSON_SCHEMA_STRICT}
    )["groq"]
    strict_result = _preflight_case_result(strict_evaluator, SYNTHETIC_PREFLIGHT_CASES[0])
    diagnostics["strict_schema"] = strict_result
    request_count += 1

    selected_mode: str | None = None
    if strict_result["api_success"] and strict_result["parse_success"]:
        selected_mode = JudgeOutputMode.JSON_SCHEMA_STRICT
    elif object_result["api_success"] and object_result["parse_success"]:
        selected_mode = JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION
    elif basic["api_success"] and basic["parse_success"]:
        selected_mode = JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION
    diagnostics["selected_output_mode"] = selected_mode
    return diagnostics, request_count, selected_mode


def _configuration_hash(evaluator: LLMJudgeEvaluator) -> str:
    serialized = json.dumps(evaluator.config, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _preflight(*, prior_external_requests: int, prior_repair_requests: int) -> dict[str, Any]:
    call_count = 0
    results: dict[str, Any] = {}
    output_modes: dict[str, str] = {}

    gemini_evaluator = _provider_evaluators(
        ("gemini",), {"gemini": JudgeOutputMode.JSON_SCHEMA_STRICT}
    )["gemini"]
    gemini_result = _provider_preflight_result(gemini_evaluator, SYNTHETIC_PREFLIGHT_CASES)
    call_count += len(SYNTHETIC_PREFLIGHT_CASES)
    results["gemini"] = gemini_result
    if gemini_result["api_success_count"] == 2 and gemini_result["parse_success_count"] == 2:
        output_modes["gemini"] = JudgeOutputMode.JSON_SCHEMA_STRICT

    groq_diagnostics, groq_calls, groq_mode = _groq_diagnostics()
    call_count += groq_calls
    results["groq"] = {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "base_url_identifier": "api.groq.com/openai/v1",
        "diagnostics": groq_diagnostics,
        "requested_output_mode": groq_mode,
        "actual_output_mode": groq_mode,
        "provider_schema_enforced": groq_mode == JudgeOutputMode.JSON_SCHEMA_STRICT,
        "local_schema_validated": True,
        "api_success_count": 0,
        "parse_success_count": 0,
        "cases": [],
    }
    if groq_mode is not None:
        groq_evaluator = _provider_evaluators(("groq",), {"groq": groq_mode})["groq"]
        groq_result = _provider_preflight_result(
            groq_evaluator, SYNTHETIC_PREFLIGHT_CASES, diagnostics=groq_diagnostics
        )
        call_count += len(SYNTHETIC_PREFLIGHT_CASES)
        results["groq"] = groq_result
        output_modes["groq"] = groq_mode

    selected_providers = ["gemini"] + (["groq"] if "groq" in output_modes else [])
    if (
        "groq" not in output_modes
        and "gemini" in output_modes
        and os.environ.get("OPENROUTER_API_KEY", "").strip()
    ):
        openrouter_evaluator = _provider_evaluators(
            (OPENROUTER_FALLBACK_NAME,),
            {OPENROUTER_FALLBACK_NAME: JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION},
        )[OPENROUTER_FALLBACK_NAME]
        openrouter_result = _provider_preflight_result(
            openrouter_evaluator,
            SYNTHETIC_PREFLIGHT_CASES,
            diagnostics={"fallback_reason": "groq_basic_completion_blocked"},
        )
        call_count += len(SYNTHETIC_PREFLIGHT_CASES)
        results[OPENROUTER_FALLBACK_NAME] = openrouter_result
        if (
            openrouter_result["api_success_count"] == 2
            and openrouter_result["parse_success_count"] == 2
        ):
            selected_providers = ["gemini", OPENROUTER_FALLBACK_NAME]
            output_modes[OPENROUTER_FALLBACK_NAME] = JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION

    repair_requests = prior_repair_requests + call_count
    config_hashes: dict[str, str] = {}
    for provider in selected_providers:
        evaluator = _provider_evaluators((provider,), {provider: output_modes[provider]})[provider]
        config_hashes[provider] = _configuration_hash(evaluator)
    return {
        "schema_version": "phase5a-preflight-v2",
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version_judge": JUDGE_SCHEMA_VERSION,
        "prior_external_requests": prior_external_requests,
        "prior_repair_requests": prior_repair_requests,
        "repair_external_requests": repair_requests,
        "external_requests": prior_external_requests + repair_requests,
        "preflight_requests": call_count,
        "selected_providers": selected_providers if len(selected_providers) == 2 else [],
        "output_modes": output_modes,
        "provider_config_hashes": config_hashes,
        "providers": results,
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
    ledger = path.with_name("phase5a-repair-ledger.json")
    if ledger.is_file():
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        value = payload.get("repair_external_requests", 0) if isinstance(payload, dict) else 0
        if isinstance(value, int) and 0 <= value <= 300:
            return value
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("prior_repair_requests", 0) if isinstance(payload, dict) else 0
        if isinstance(value, int) and 0 <= value <= 300:
            return value
    return 0


def _validate_preflight(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("external_requests"), int)
        or not isinstance(payload.get("repair_external_requests"), int)
        or payload.get("repair_external_requests") < 0
        or payload.get("repair_external_requests") > 300
        or not isinstance(payload.get("selected_providers"), list)
        or len(payload.get("selected_providers", [])) != 2
        or payload.get("selected_providers", [None])[0] != "gemini"
    ):
        raise RuntimeError("preflight artifact is missing a valid repaired-provider gate")
    for provider in payload["selected_providers"]:
        result = payload.get("providers", {}).get(provider, {})
        if result.get("api_success_count") != 2 or result.get("parse_success_count") != 2:
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
    return {
        "provider": evaluator.provider.provider_name,
        "base_url_identifier": evaluator.provider.base_url_identifier,
        "requested_model": evaluator.provider.model,
        "returned_models": returned_models,
        "model_revision": None,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version": JUDGE_SCHEMA_VERSION,
        "output_mode": evaluator.config["output_mode"],
        "routing_immutable": getattr(evaluator.provider, "routing_immutable", None),
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


def _run_base(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _validate_preflight(args.preflight_artifact)
    selected_providers = tuple(preflight["selected_providers"])
    dataset = _load_dataset(args.data_dir)
    manifest = _load_or_create_manifest(dataset, args.manifest, sample_only=False)
    if len(manifest.example_ids) != 120:
        raise RuntimeError(
            f"pilot manifest must contain 120 examples, found {len(manifest.example_ids)}"
        )
    examples = {
        example.example_id: (example.source_context, example.response)
        for example in dataset.examples
        if example.example_id in set(manifest.example_ids)
    }
    evaluators = _provider_evaluators(selected_providers, preflight["output_modes"])
    budget = RequestBudget(300)
    budget.requests_used = int(preflight["repair_external_requests"])
    state = PilotStateStore(args.state)
    records = run_provider_pilot(
        manifest,
        examples,
        {name: evaluator.evaluate_with_trace for name, evaluator in evaluators.items()},
        state,
        budget,
    )
    ground_truth = {record.example_id: record.human_label for record in manifest.records}
    metadata = {record.example_id: {"task_type": record.task_type} for record in manifest.records}
    provider_records = {
        provider: [record for record in records if record.provider == provider]
        for provider in selected_providers
    }
    provider_summaries = {
        provider: {
            **summarize_provider_records(provider_records[provider], ground_truth, metadata),
            "provenance": _provider_provenance(
                evaluators[provider], provider_records[provider], manifest
            ),
        }
        for provider in OFFICIAL_PROVIDER_NAMES
    }
    expected_ids = set(manifest.example_ids)
    baseline_predictions = {
        "heuristic": _artifact_predictions(HEURISTIC_ARTIFACT, expected_ids),
        "hhem": _artifact_predictions(HHEM_ARTIFACT, expected_ids),
    }
    provider_predictions = {
        provider: _record_map(provider_records[provider]) for provider in selected_providers
    }
    id_match = {
        name: set(values) == expected_ids
        for name, values in {**baseline_predictions, **provider_predictions}.items()
    }
    comparisons: dict[str, Any] = {}
    if all(id_match.values()):
        secondary_provider = selected_providers[1]
        comparisons = {
            "gemini_vs_hhem": compare_pilot_predictions(
                ground_truth, baseline_predictions["hhem"], provider_predictions["gemini"]
            ),
            f"{secondary_provider}_vs_hhem": compare_pilot_predictions(
                ground_truth, baseline_predictions["hhem"], provider_predictions[secondary_provider]
            ),
            "gemini_vs_heuristic": compare_pilot_predictions(
                ground_truth, baseline_predictions["heuristic"], provider_predictions["gemini"]
            ),
            f"{secondary_provider}_vs_heuristic": compare_pilot_predictions(
                ground_truth,
                baseline_predictions["heuristic"],
                provider_predictions[secondary_provider],
            ),
            f"gemini_vs_{secondary_provider}": compare_pilot_predictions(
                ground_truth,
                provider_predictions["gemini"],
                provider_predictions[secondary_provider],
            ),
        }
    else:
        comparisons["status"] = "SKIPPED_ID_MISMATCH"
    complete_predictions = {**baseline_predictions, **provider_predictions}
    multi = (
        build_multi_evaluator_analysis(ground_truth, complete_predictions)
        if all(id_match.values())
        else {"status": "SKIPPED_ID_MISMATCH"}
    )
    report = {
        "schema_version": "phase5a-pilot-v1",
        "classification": "BALANCED_STRATIFIED_PILOT",
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
        "secondary_provider": selected_providers[1],
        "output_modes": preflight["output_modes"],
        "provider_config_hashes": preflight["provider_config_hashes"],
        "git_commit": _git_head(),
        "id_match_check": id_match,
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
        "prior_external_requests": preflight["prior_external_requests"],
        "repair_external_requests": budget.requests_used,
        "external_requests": preflight["prior_external_requests"] + budget.requests_used,
        "quota_status": "AVAILABLE_WITHIN_300_REQUEST_CEILING",
        "cost_status": "PROVIDER_REPORTED_ONLY",
        "consistency_run": "NOT_RUN",
    }
    _write_json(args.report, report)
    return report


def _run_consistency(args: argparse.Namespace) -> dict[str, Any]:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    selected_providers = tuple(report.get("selected_providers", ()))
    if len(selected_providers) != 2:
        raise RuntimeError("consistency requires a completed two-provider pilot")
    manifest = PilotManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    consistency = build_consistency_manifest(manifest)
    current_requests = int(report.get("external_requests", 0))
    if current_requests + 48 > 300:
        report["consistency_run"] = "QUOTA_BLOCKED"
        _write_json(args.report, report)
        return report
    dataset = _load_dataset(args.data_dir)
    examples = {
        example.example_id: (example.source_context, example.response)
        for example in dataset.examples
        if example.example_id in set(consistency.example_ids)
    }
    evaluators = _provider_evaluators(selected_providers, report.get("output_modes", {}))
    budget = RequestBudget(300)
    budget.requests_used = current_requests
    repeated: dict[str, list[PilotRunRecord]] = {provider: [] for provider in selected_providers}
    for repeat in (1, 2):
        repeat_state = PilotStateStore(
            args.report.with_name(f"phase5a-consistency-repeat-{repeat}-state.json")
        )
        repeat_records = run_provider_pilot(
            consistency,
            examples,
            {name: evaluator.evaluate_with_trace for name, evaluator in evaluators.items()},
            repeat_state,
            budget,
            max_retries=0,
        )
        for record in repeat_records:
            repeated[record.provider].append(record)
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
    report["repair_external_requests"] = budget.requests_used
    report["external_requests"] = report.get("prior_external_requests", 0) + budget.requests_used
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
        return 0 if len(payload["selected_providers"]) == 2 else 2
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
