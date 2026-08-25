"""Bounded Phase 5A Gemini/Groq pilot orchestration.

This script is intentionally explicit about external calls. Importing it has no
network side effects; ``--sample-only`` is offline, and real calls require a
successful synthetic preflight artifact.
"""

from __future__ import annotations

import argparse
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
DEFAULT_MANIFEST = REPO_ROOT / "datasets" / "manifests" / "ragtruth-llm-judge-pilot-v1.json"
DEFAULT_STATE = REPO_ROOT / "reports" / "phase5a-pilot-state.json"
DEFAULT_REPORT = REPO_ROOT / "reports" / "phase5a-pilot-v1.json"
DEFAULT_PREFLIGHT = REPO_ROOT / "reports" / "phase5a-preflight.json"
DEFAULT_DATA_DIR = REPO_ROOT / "datasets" / "external" / "ragtruth"
HEURISTIC_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-heuristic-v1.json"
HHEM_ARTIFACT = REPO_ROOT / "reports" / "ragtruth-test-hhem-v1.json"


def estimate_request_count(pilot_size: int, *, include_consistency: bool) -> int:
    """Estimate preflight, base, and optional consistency requests."""

    return 2 + (2 * pilot_size) + (48 if include_consistency else 0)


def preflight_request_count(previous_external_requests: int) -> int:
    """Add the two provider calls while preserving prior real requests."""

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


def _provider_evaluators() -> dict[str, LLMJudgeEvaluator]:
    keys = {name: os.environ.get(name, "").strip() for name in ("GEMINI_API_KEY", "GROQ_API_KEY")}
    if any(not value for value in keys.values()):
        raise RuntimeError("required provider credential environment variable is missing")
    sampling = SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=256,
        reasoning_effort="low",
        include_reasoning=False,
    )
    return {
        "gemini": LLMJudgeEvaluator(
            GeminiProviderAdapter(keys["GEMINI_API_KEY"]), sampling=sampling
        ),
        "groq": LLMJudgeEvaluator(GroqProviderAdapter(keys["GROQ_API_KEY"]), sampling=sampling),
    }


def _preflight(*, prior_requests: int = 0) -> dict[str, Any]:
    evaluators = _provider_evaluators()
    results: dict[str, Any] = {}
    for provider in OFFICIAL_PROVIDER_NAMES:
        trace = evaluators[provider].evaluate_with_trace(
            "The source context states that the value is seven.",
            "The value is seven.",
            "phase5a-preflight",
        )
        results[provider] = {
            "provider": provider,
            "model": evaluators[provider].provider.model,
            "base_url_identifier": evaluators[provider].provider.base_url_identifier,
            "api_success": trace.api_success,
            "parse_success": trace.parse_success,
            "structured_output_status": trace.structured_output_status,
            "label": trace.prediction.label.value if trace.prediction else None,
            "returned_model": trace.returned_model,
            "usage": trace.usage,
            "latency_ms": trace.latency_ms,
            "error_class": trace.error_class,
            "safe_error_summary": trace.safe_error_summary,
        }
    payload = {
        "schema_version": "phase5a-preflight-v1",
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version_judge": JUDGE_SCHEMA_VERSION,
        "external_requests": preflight_request_count(prior_requests),
        "preflight_requests": 2,
        "providers": results,
    }
    return payload


def _prior_preflight_requests(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("external_requests"), int):
        raise RuntimeError("existing preflight artifact has no valid request ledger")
    previous = int(payload["external_requests"])
    if previous < 0 or previous > 300:
        raise RuntimeError("existing preflight artifact has an invalid request ledger")
    return previous


def _validate_preflight(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("external_requests"), int)
        or payload.get("external_requests") < 2
        or payload.get("external_requests") > 300
        or payload.get("preflight_requests") != 2
    ):
        raise RuntimeError("preflight artifact is missing its cumulative request ledger")
    for provider in OFFICIAL_PROVIDER_NAMES:
        result = payload.get("providers", {}).get(provider, {})
        if (
            result.get("api_success") is not True
            or result.get("parse_success") is not True
            or result.get("label") != "GROUNDED"
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
    return {
        "provider": evaluator.provider.provider_name,
        "base_url_identifier": evaluator.provider.base_url_identifier,
        "requested_model": evaluator.provider.model,
        "returned_models": returned_models,
        "model_revision": None,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_sha256": JUDGE_PROMPT_SHA256,
        "schema_version": JUDGE_SCHEMA_VERSION,
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
    evaluators = _provider_evaluators()
    budget = RequestBudget(300)
    budget.requests_used = int(preflight["external_requests"])
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
        for provider in OFFICIAL_PROVIDER_NAMES
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
        provider: _record_map(provider_records[provider]) for provider in OFFICIAL_PROVIDER_NAMES
    }
    id_match = {
        name: set(values) == expected_ids
        for name, values in {**baseline_predictions, **provider_predictions}.items()
    }
    comparisons: dict[str, Any] = {}
    if all(id_match.values()):
        comparisons = {
            "gemini_vs_hhem": compare_pilot_predictions(
                ground_truth, baseline_predictions["hhem"], provider_predictions["gemini"]
            ),
            "groq_vs_hhem": compare_pilot_predictions(
                ground_truth, baseline_predictions["hhem"], provider_predictions["groq"]
            ),
            "gemini_vs_heuristic": compare_pilot_predictions(
                ground_truth, baseline_predictions["heuristic"], provider_predictions["gemini"]
            ),
            "groq_vs_heuristic": compare_pilot_predictions(
                ground_truth, baseline_predictions["heuristic"], provider_predictions["groq"]
            ),
            "gemini_vs_groq": compare_pilot_predictions(
                ground_truth, provider_predictions["gemini"], provider_predictions["groq"]
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
        "external_requests": budget.requests_used,
        "quota_status": "AVAILABLE_WITHIN_300_REQUEST_CEILING",
        "cost_status": "PROVIDER_REPORTED_ONLY",
        "consistency_run": "NOT_RUN",
    }
    _write_json(args.report, report)
    return report


def _run_consistency(args: argparse.Namespace) -> dict[str, Any]:
    report = json.loads(args.report.read_text(encoding="utf-8"))
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
    evaluators = _provider_evaluators()
    budget = RequestBudget(300)
    budget.requests_used = current_requests
    repeated: dict[str, list[PilotRunRecord]] = {
        provider: [] for provider in OFFICIAL_PROVIDER_NAMES
    }
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
    for provider in OFFICIAL_PROVIDER_NAMES:
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
    report["external_requests"] = budget.requests_used
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
        prior_requests = _prior_preflight_requests(args.preflight_artifact)
        if preflight_request_count(prior_requests) > 300:
            print(json.dumps({"error": "preflight request budget would exceed 300"}))
            return 2
        payload = _preflight(prior_requests=prior_requests)
        _write_json(args.preflight_artifact, payload)
        print(
            json.dumps(
                {
                    "external_requests": payload["external_requests"],
                    "providers": payload["providers"],
                },
                ensure_ascii=False,
            )
        )
        return (
            0
            if all(
                result["api_success"] and result["parse_success"] and result["label"] == "GROUNDED"
                for result in payload["providers"].values()
            )
            else 2
        )
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
