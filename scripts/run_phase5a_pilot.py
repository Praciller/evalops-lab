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
from evalops.pilot.readiness import assess_llm_judge_readiness
from evalops.pilot.sampling import build_consistency_manifest, build_pilot_manifest
from evalops.providers.okmd import (
    OKMDModel,
    estimate_pilot_tokens,
    model_family,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PROVIDER_NAMES = ("gemini",)
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
        "usage": trace.usage,
        "latency_ms": trace.latency_ms,
        "error_class": trace.error_class,
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
    quotas = [record.trace.quota for record in records if record.trace.quota is not None]
    return {
        "provider": evaluator.provider.provider_name,
        "gateway": getattr(evaluator.provider, "gateway", None),
        "base_url_identifier": evaluator.provider.base_url_identifier,
        "requested_model": evaluator.provider.model,
        "catalog_model_name": getattr(evaluator.provider, "catalog_model_name", None),
        "returned_models": returned_models,
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


def _run_base(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _validate_preflight(args.preflight_artifact)
    selected_providers = tuple(preflight["selected_providers"])
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
    budget = RequestBudget(300)
    budget.requests_used = int(preflight["repair_external_requests"])
    state = PilotStateStore(args.state)
    records = run_provider_pilot(
        manifest,
        examples,
        {name: evaluator.evaluate_with_trace for name, evaluator in evaluators.items()},
        state,
        budget,
        parse_regenerations={"okmd": 1} if "okmd" in selected_providers else None,
    )
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
        for provider in selected_providers
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
    if not selected_providers:
        raise RuntimeError("consistency requires a completed LLM judge pilot")
    manifest = PilotManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    _validate_pilot_manifest(manifest)
    consistency = build_consistency_manifest(manifest)
    current_requests = int(report.get("external_requests", 0))
    consistency_requests = 24 * len(selected_providers)
    if current_requests + consistency_requests > 300:
        report["consistency_run"] = "QUOTA_BLOCKED"
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
            parse_regenerations={"okmd": 1} if "okmd" in selected_providers else None,
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
