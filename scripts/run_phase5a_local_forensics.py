"""Audit Phase 5A-L failures and optionally run a bounded strict-v1 diagnosis.

The diagnostic mode is deliberately separate from the primary pilot.  It reads
the frozen manifest and local state, selects unresolved IDs deterministically,
uses the exact strict-v1 Ollama request contract, and writes only an ignored
diagnostic artifact.  It never writes primary state or promotes a prediction.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.judge.models import JudgeDecision
from evalops.evaluators.judge.prompt import (
    JUDGE_OUTPUT_SCHEMA,
    JUDGE_PROMPT_SHA256,
    JUDGE_PROMPT_VERSION,
    JUDGE_SCHEMA_VERSION,
    render_judge_prompt,
)
from evalops.evaluators.judge.providers import (
    JudgeOutputMode,
    OllamaProviderAdapter,
    SamplingConfig,
)
from evalops.pilot.models import PilotManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = REPO_ROOT / "reports" / "phase5a-local-forensics-v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "datasets" / "manifests" / "ragtruth-llm-judge-pilot-v1.json"
DEFAULT_DATA_DIR = REPO_ROOT / "datasets" / "external" / "ragtruth"
DEFAULT_PREFLIGHT = REPO_ROOT / "reports" / "phase5a-local-preflight.json"
DEFAULT_STATE = REPO_ROOT / "reports" / "phase5a-local-pilot-state.json"
EXPECTED_PILOT_SIZE = 120
MAX_DIAGNOSTICS = 5


def _sampling() -> SamplingConfig:
    return SamplingConfig(
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=256,
        reasoning_effort="low",
        include_reasoning=False,
    )


def _provider(metadata: dict[str, Any]) -> OllamaProviderAdapter:
    context_length = metadata.get("context_length")
    return OllamaProviderAdapter(
        model=str(metadata["requested_model"]),
        timeout_seconds=300.0,
        output_mode=JudgeOutputMode.JSON_SCHEMA_STRICT,
        model_digest=str(metadata.get("model_digest")),
        quantization=str(metadata.get("quantization")),
        parameter_size=str(metadata.get("parameter_size")),
        context_length=context_length if isinstance(context_length, int) else None,
        inference_device="cpu",
        thinking_mode="OFF",
        ollama_version=str(metadata.get("ollama_version")),
    )


def classify_assistant_content(content: str | None) -> dict[str, Any]:
    """Classify one output without repairing or changing any value."""

    if not content or not content.strip():
        return {
            "category": "EMPTY_CONTENT",
            "json_parse_success": False,
            "validation_error_types": [],
            "validation_error_locations": [],
        }
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        stripped = content.lstrip()
        if stripped.startswith("```"):
            category = "JSON_CODE_FENCE"
        elif not content.rstrip().endswith(("}", "]")):
            category = "TRUNCATED_JSON"
        else:
            category = "INVALID_JSON"
        return {
            "category": category,
            "json_parse_success": False,
            "validation_error_types": [],
            "validation_error_locations": [],
        }
    if not isinstance(parsed, dict):
        return {
            "category": "PARSE_ERROR_ROOT_NOT_OBJECT",
            "json_parse_success": True,
            "validation_error_types": [],
            "validation_error_locations": [],
        }
    try:
        JudgeDecision.model_validate(parsed)
    except ValidationError as error:
        error_items = error.errors()
        error_types = [str(item.get("type")) for item in error_items]
        locations = [".".join(str(part) for part in item.get("loc", ())) for item in error_items]
        if "missing" in error_types:
            category = "SCHEMA_MISSING_FIELD"
        elif any("enum" in item for item in error_types):
            category = "INVALID_LABEL_ENUM"
        elif any(
            item in {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}
            for item in error_types
        ):
            category = "CONFIDENCE_OUT_OF_RANGE"
        elif any(item in {"list_type", "string_type"} for item in error_types):
            category = "UNSUPPORTED_CLAIMS_TYPE_ERROR"
        elif "too_long" in error_types:
            category = "REASON_VALIDATION_FAILURE"
        elif "value_error" in error_types:
            category = "LABEL_CLAIM_CONSISTENCY_FAILURE"
        else:
            category = "SCHEMA_VALIDATION_ERROR"
        return {
            "category": category,
            "json_parse_success": True,
            "validation_error_types": error_types,
            "validation_error_locations": locations,
        }
    return {
        "category": "VALID_STRUCTURED_OUTPUT",
        "json_parse_success": True,
        "validation_error_types": [],
        "validation_error_locations": [],
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _manifest_and_state(
    manifest_path: Path, state_path: Path
) -> tuple[PilotManifest, dict[str, Any]]:
    manifest = PilotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    state = _load_json(state_path)
    records = state.get("records")
    if not isinstance(records, dict):
        raise ValueError("local pilot state records must be an object")
    if len(manifest.records) != EXPECTED_PILOT_SIZE:
        raise ValueError("LOCAL_FORENSICS_PILOT_SIZE_MISMATCH")
    state_ids = {
        str(record.get("example_id")) for record in records.values() if isinstance(record, dict)
    }
    manifest_ids = {record.example_id for record in manifest.records}
    if state_ids != manifest_ids:
        raise ValueError("LOCAL_FORENSICS_STATE_ID_MISMATCH")
    return manifest, state


def _safe_record_evidence(state: dict[str, Any]) -> dict[str, Any]:
    records = [record for record in state["records"].values() if isinstance(record, dict)]
    failures = [record for record in records if record.get("status") != "SUCCESS"]

    def trace_value(record: dict[str, Any], name: str) -> Any:
        trace = record.get("trace")
        return trace.get(name) if isinstance(trace, dict) else None

    def all_equal(name: str, value: Any) -> bool:
        return bool(failures) and all(trace_value(record, name) == value for record in failures)

    return {
        "record_count": len(records),
        "successful_count": sum(record.get("status") == "SUCCESS" for record in records),
        "failure_count": len(failures),
        "failure_error_counts": _counts(
            str(trace_value(record, "error_class")) for record in failures
        ),
        "all_failures_api_success_200": all(
            trace_value(record, "api_success") is True and trace_value(record, "http_status") == 200
            for record in failures
        ),
        "all_failures_content_present": all_equal("assistant_content_present", True),
        "all_failures_finish_reason_stop": all_equal("finish_reason", "stop"),
        "all_failures_thinking_absent": all_equal("reasoning_present", False),
        "all_failures_have_usage": all_equal("usage_metadata_present", True),
        "raw_model_response_persisted": False,
        "reasoning_persisted": False,
    }


def _failure_breakdown(state: dict[str, Any], manifest_ids: list[str]) -> dict[str, Any]:
    """Classify only what safe persisted metadata proves."""

    groups: dict[str, list[str]] = {}
    for record in state["records"].values():
        if not isinstance(record, dict) or record.get("status") == "SUCCESS":
            continue
        trace = record.get("trace")
        trace = trace if isinstance(trace, dict) else {}
        error_class = trace.get("error_class")
        finish_reason = trace.get("finish_reason")
        if error_class == "PARSE_ERROR" and finish_reason == "length":
            category = "OUTPUT_TOKEN_LIMIT"
        elif error_class == "PARSE_ERROR":
            category = "PERSISTED_PARSE_ERROR_SUBTYPE_UNKNOWN"
        elif error_class == "SCHEMA_VALIDATION_ERROR":
            category = "PERSISTED_SCHEMA_VALIDATION_SUBTYPE_UNKNOWN"
        else:
            category = str(error_class or "UNKNOWN_FAILURE")
        groups.setdefault(category, []).append(str(record.get("example_id")))
    result: dict[str, Any] = {}
    for category, example_ids in groups.items():
        ordered_ids = [example_id for example_id in manifest_ids if example_id in example_ids]
        result[category] = {
            "count": len(ordered_ids),
            "example_ids": ordered_ids,
            "original_generated_response_preserved": False,
            "recovery_possible_without_inference": False,
        }
    return dict(sorted(result.items()))


def _counts(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _diagnostic_record(
    provider: Any,
    sampling: Any,
    example_id: str,
    context: str,
    response: str,
    model_digest: str,
) -> dict[str, Any]:
    call = provider.judge(
        render_judge_prompt(context, response),
        schema=JUDGE_OUTPUT_SCHEMA,
        config=sampling,
    )
    if not call.api_success:
        error_class = call.error_class or "UNKNOWN_FAILURE"
        category = {
            "LOCAL_CONNECTION_ERROR": "OLLAMA_RUNTIME_ERROR",
            "LOCAL_OOM": "LOCAL_OOM",
            "LOCAL_RESOURCE_ERROR": "LOCAL_RESOURCE_ERROR",
            "LOCAL_MODEL_NOT_FOUND": "MODEL_LOAD_ERROR",
            "LOCAL_TIMEOUT": "TIMEOUT",
        }.get(error_class, error_class)
        classification = {
            "category": category,
            "json_parse_success": False,
            "validation_error_types": [],
            "validation_error_locations": [],
        }
    else:
        classification = classify_assistant_content(call.assistant_content)
    return {
        "example_id": example_id,
        "request_contract": {
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": provider.model,
            "model_digest": model_digest,
            "stream": False,
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "seed": None,
            "num_ctx": None,
            "num_predict": sampling.max_output_tokens,
            "format": "JUDGE_OUTPUT_SCHEMA",
            "think": False,
            "keep_alive": None,
        },
        "safe_metadata": call.safe_metadata(),
        "content_present": call.assistant_content_present,
        "content_length": call.assistant_content_length,
        "thinking_present": call.reasoning_present,
        "thinking_length": call.reasoning_length,
        **classification,
        "raw_assistant_content": call.assistant_content,
        "raw_response_persisted": call.assistant_content is not None,
    }


def run_forensics(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    state_path: Path = DEFAULT_STATE,
    preflight_path: Path = DEFAULT_PREFLIGHT,
    data_dir: Path = DEFAULT_DATA_DIR,
    artifact_path: Path = DEFAULT_ARTIFACT,
    run_diagnostics: bool = False,
    diagnostic_count: int = MAX_DIAGNOSTICS,
) -> dict[str, Any]:
    if diagnostic_count < 0 or diagnostic_count > MAX_DIAGNOSTICS:
        raise ValueError("diagnostic_count must be between 0 and 5")
    manifest, state = _manifest_and_state(manifest_path, state_path)
    manifest_ids = [record.example_id for record in manifest.records]
    successful_ids = {
        str(record.get("example_id"))
        for record in state["records"].values()
        if isinstance(record, dict) and record.get("status") == "SUCCESS"
    }
    pending_ids = [example_id for example_id in manifest_ids if example_id not in successful_ids]
    preflight = _load_json(preflight_path)
    model_metadata = preflight.get("model")
    if not isinstance(model_metadata, dict):
        raise ValueError("LOCAL_FORENSICS_MODEL_METADATA_MISSING")
    model_digest = str(model_metadata.get("model_digest"))
    selected_ids = pending_ids[:diagnostic_count]
    diagnostics: list[dict[str, Any]] = []
    if run_diagnostics and selected_ids:
        dataset = load_ragtruth_dataset(
            data_dir / "response.jsonl",
            data_dir / "source_info.jsonl",
            split="test",
            source_revision=manifest.dataset_revision,
        )
        by_id = {example.example_id: example for example in dataset.examples}
        provider = _provider(model_metadata)
        sampling = _sampling()
        for example_id in selected_ids:
            example = by_id[example_id]
            diagnostics.append(
                _diagnostic_record(
                    provider,
                    sampling,
                    example_id,
                    example.source_context,
                    example.response,
                    model_digest,
                )
            )
    payload: dict[str, Any] = {
        "schema_version": "phase5a-local-forensics-v1",
        "diagnostic_only": True,
        "counts_as_primary_prediction": False,
        "experiment_id": "ragtruth-local-llm-judge-pilot-v1",
        "source_git_commit": _git_head(),
        "pilot_size": len(manifest_ids),
        "successful_count": len(successful_ids),
        "pending_count": len(pending_ids),
        "first_pending_id": pending_ids[0] if pending_ids else None,
        "pending_ids": pending_ids,
        "persisted_evidence": _safe_record_evidence(state),
        "failure_breakdown": _failure_breakdown(state, manifest_ids),
        "parser_repair_allowed": False,
        "parser_repair_gate": {
            "deterministic": False,
            "content_preserving": False,
            "label_independent": False,
            "original_outputs_available": False,
            "uniform_reparse_possible": False,
            "reason": (
                "The persisted state retains safe metadata only, not original output content."
            ),
        },
        "configuration": {
            "model": model_metadata.get("requested_model"),
            "model_digest": model_digest,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "prompt_sha256": JUDGE_PROMPT_SHA256,
            "schema_version": JUDGE_SCHEMA_VERSION,
            "output_mode": JudgeOutputMode.JSON_SCHEMA_STRICT,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 256,
            "think": False,
            "stream": False,
            "seed": None,
            "num_ctx": None,
            "keep_alive": None,
        },
        "selected_ids": selected_ids,
        "selection_rule": "first unresolved IDs in frozen manifest order",
        "diagnostics_run": bool(run_diagnostics),
        "diagnostics": diagnostics,
        "raw_model_response_persisted": any(
            item.get("raw_response_persisted") is True for item in diagnostics
        ),
        "reasoning_persisted": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--run-diagnostics", action="store_true")
    parser.add_argument("--diagnostic-count", type=int, default=MAX_DIAGNOSTICS)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_forensics(
        manifest_path=args.manifest,
        state_path=args.state,
        preflight_path=args.preflight,
        data_dir=args.data_dir,
        artifact_path=args.artifact,
        run_diagnostics=args.run_diagnostics,
        diagnostic_count=args.diagnostic_count,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.artifact),
                "successful_count": payload["successful_count"],
                "pending_count": payload["pending_count"],
                "selected_ids": payload["selected_ids"],
                "diagnostics_count": len(payload["diagnostics"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
