"""Dependency-light provider response classification.

This module deliberately has no network client. Provider runners can feed it
safe in-memory response objects, keeping offline CI free of external calls and
keeping reasoning text out of persisted health artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict


class CompletionAssessment(BaseModel):
    """Safe diagnostics and independent completion classifications."""

    model_config = ConfigDict(frozen=True)

    response_object_type: str | None = None
    returned_model: str | None = None
    finish_reason: str | None = None
    completion_status: str = "INVALID_RESPONSE"
    structured_output_status: str = "NOT_RUN"
    instruction_adherence_status: str = "FAIL"
    assistant_content_present: bool = False
    assistant_content_length: int = 0
    reasoning_present: bool = False
    reasoning_length: int = 0
    tool_calls_present: bool = False
    usage_metadata_present: bool = False
    usage: dict[str, int | float | str] | None = None
    structured_parse_success: bool | None = None


class ProviderHealthResult(BaseModel):
    """Provider-level health state with separate technical and policy gates."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    authentication_status: str = "NOT_RUN"
    discovery_status: str = "NOT_RUN"
    connectivity_status: str = "NOT_RUN"
    completion_status: str = "NOT_RUN"
    structured_output_status: str = "NOT_RUN"
    instruction_adherence_status: str = "NOT_RUN"
    benchmark_eligible: bool = True
    benchmark_block_reason: str | None = None
    selected_model: str | int | None = None
    returned_model: str | None = None
    backend_provider: str | None = None
    backend_revision: str | None = None
    upstream_provider: str | None = None
    routing_immutable: bool | None = None
    latency_ms: float | None = None
    usage: dict[str, int | float | str] | None = None
    error_class: str | None = None
    safe_error_summary: str | None = None
    response_object_type: str | None = None
    finish_reason: str | None = None
    assistant_content_present: bool | None = None
    assistant_content_length: int | None = None
    reasoning_present: bool | None = None
    reasoning_length: int | None = None
    tool_calls_present: bool | None = None
    usage_metadata_present: bool | None = None
    structured_parse_success: bool | None = None


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [part.get("text", "") for part in value if isinstance(part, Mapping)]
        return "".join(part for part in parts if isinstance(part, str))
    return ""


def _safe_length(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return len(str(value))


def _safe_usage(value: Any) -> dict[str, int | float | str] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, int | float | str] = {}
    for key, item in value.items():
        if isinstance(item, (bool, int, float, str)) and (
            "token" in str(key).lower() or "cost" in str(key).lower()
        ):
            safe[str(key)] = item
    return safe or None


def _message_from_response(
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return None, None
    choice = choices[0]
    message = choice.get("message")
    return choice, message if isinstance(message, Mapping) else None


def _structured_status(
    content: str,
    schema: Mapping[str, Any] | None,
) -> tuple[str, bool | None]:
    if schema is None:
        return "NOT_RUN", None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "PARSE_FAILED", False
    if not isinstance(parsed, Mapping):
        return "PARSE_FAILED", True
    if all(parsed.get(key) == value for key, value in schema.items()):
        return "PASS", True
    return "PARSE_FAILED", True


def assess_completion_response(
    payload: Any,
    *,
    expected_text: str = "EVALOPS_OK",
    structured_schema: Mapping[str, Any] | None = None,
) -> CompletionAssessment:
    """Classify a response without persisting final or reasoning text."""

    if not isinstance(payload, Mapping):
        return CompletionAssessment(response_object_type=type(payload).__name__)

    choice, message = _message_from_response(payload)
    response_object_type = payload.get("object")
    response_object_type = response_object_type if isinstance(response_object_type, str) else None
    returned_model = payload.get("model")
    returned_model = returned_model if isinstance(returned_model, str) else None
    if message is None or choice is None:
        return CompletionAssessment(
            response_object_type=response_object_type,
            returned_model=returned_model,
            usage_metadata_present=isinstance(payload.get("usage"), Mapping),
            usage=_safe_usage(payload.get("usage")),
        )

    content = _content_text(message.get("content"))
    content_present = bool(content.strip())
    reasoning = message.get("reasoning", message.get("reasoning_content"))
    tool_calls = message.get("tool_calls")
    tool_calls_present = isinstance(tool_calls, list) and bool(tool_calls)
    completion_status = "PASS" if content_present or tool_calls_present else "INVALID_RESPONSE"
    if not content_present:
        instruction_status = "FAIL"
    elif content.strip() == expected_text:
        instruction_status = "PASS"
    else:
        instruction_status = "PARTIAL"
    structured_status, structured_parse_success = _structured_status(content, structured_schema)
    finish_reason = choice.get("finish_reason")
    finish_reason = finish_reason if isinstance(finish_reason, str) else None
    return CompletionAssessment(
        response_object_type=response_object_type,
        returned_model=returned_model,
        finish_reason=finish_reason,
        completion_status=completion_status,
        structured_output_status=structured_status,
        instruction_adherence_status=instruction_status,
        assistant_content_present=content_present,
        assistant_content_length=len(content),
        reasoning_present=reasoning is not None,
        reasoning_length=_safe_length(reasoning),
        tool_calls_present=tool_calls_present,
        usage_metadata_present=isinstance(payload.get("usage"), Mapping),
        usage=_safe_usage(payload.get("usage")),
        structured_parse_success=structured_parse_success,
    )


def classify_http_status(status_code: int, *, phase: str) -> str:
    """Map an HTTP/transport outcome to a controlled provider status."""

    if 200 <= status_code < 300:
        return "PASS"
    if status_code in {401, 403}:
        return "AUTH_FAILED"
    if status_code == 402:
        return "QUOTA_EXHAUSTED"
    if status_code == 404 and phase == "completion":
        return "MODEL_UNAVAILABLE"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code == 0 or status_code in {408, 500, 502, 503, 504}:
        return "NETWORK_FAILED"
    if phase == "timeout":
        return "NETWORK_FAILED"
    return "INVALID_RESPONSE"


def select_openrouter_model(models: Sequence[Mapping[str, Any]]) -> str | None:
    """Choose a deterministic, free, text-capable exact model slug."""

    eligible: list[tuple[int, str]] = []
    for model in models:
        identifier = model.get("id")
        if not isinstance(identifier, str) or ":free" not in identifier:
            continue
        architecture = model.get("architecture")
        modality = architecture.get("modality") if isinstance(architecture, Mapping) else None
        if isinstance(modality, str) and not modality.startswith("text->"):
            continue
        parameters = model.get("supported_parameters")
        parameters = parameters if isinstance(parameters, list) else []
        structured = int(
            any(parameter in {"response_format", "structured_outputs"} for parameter in parameters)
        )
        eligible.append((-structured, identifier))
    eligible.sort()
    return eligible[0][1] if eligible else None


def _diversity_key(result: ProviderHealthResult) -> str:
    provider = (result.backend_provider or result.provider).casefold()
    model = result.selected_model or result.returned_model or "unknown"
    return f"{provider}:{model}"


def model_diversity_ready(results: Sequence[ProviderHealthResult]) -> bool:
    """Require Gemini plus one eligible, meaningfully different path."""

    eligible = [
        result
        for result in results
        if result.benchmark_eligible and result.completion_status == "PASS"
    ]
    has_gemini = any(_diversity_key(result).startswith("gemini:") for result in eligible)
    return has_gemini and len({_diversity_key(result) for result in eligible}) >= 2
