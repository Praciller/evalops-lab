"""Provider adapters for structured strict-groundedness judge calls."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SamplingConfig:
    """Frozen deterministic generation settings for the pilot."""

    temperature: float = 0.0
    top_p: float = 1.0
    max_output_tokens: int = 256
    reasoning_effort: str = "low"
    include_reasoning: bool = False


@dataclass(frozen=True)
class ProviderHTTPResponse:
    """Minimal transport response used by adapters and offline fakes."""

    status_code: int
    body: dict[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)


Transport = Callable[[str, dict[str, str], dict[str, Any], float], ProviderHTTPResponse]


class JudgeOutputMode(StrEnum):
    """Provider output paths, separated from the frozen judge semantics."""

    JSON_SCHEMA_STRICT = "json-schema-strict"
    JSON_SCHEMA_BEST_EFFORT = "json-schema-best-effort"
    JSON_OBJECT_LOCAL_VALIDATION = "json-object-local-validation"
    JSON_TEXT_LOCAL_VALIDATION = "json-text-local-validation"


@dataclass(frozen=True)
class ProviderCall:
    """In-memory call result whose safe projection excludes content and reasoning."""

    provider: str
    requested_model: str
    gateway: str | None = None
    catalog_model_name: str | None = None
    returned_model: str | None = None
    model_version: str | None = None
    response_id: str | None = None
    observed_at: str | None = None
    returned_provider: str | None = None
    backend_revision: str | None = None
    api_success: bool = False
    http_status: int | None = None
    response_object_type: str | None = None
    finish_reason: str | None = None
    assistant_content: str | None = None
    assistant_content_present: bool = False
    assistant_content_length: int = 0
    reasoning_present: bool = False
    reasoning_length: int = 0
    tool_calls_present: bool = False
    usage_metadata_present: bool = False
    usage: dict[str, int | float | str] | None = None
    quota: dict[str, int | float | str] | None = None
    request_id: str | None = None
    latency_ms: float | None = None
    retry_after_seconds: float | None = None
    rate_limit_dimension: str | None = None
    structured_requested: bool = True
    requested_output_mode: str = JudgeOutputMode.JSON_SCHEMA_STRICT
    actual_output_mode: str = JudgeOutputMode.JSON_SCHEMA_STRICT
    provider_schema_enforced: bool = False
    local_schema_validated: bool = True
    error_class: str | None = None
    safe_error_summary: str | None = None

    def safe_metadata(self) -> dict[str, Any]:
        """Return persistable metadata without final content or reasoning text."""

        return {
            "provider": self.provider,
            "requested_model": self.requested_model,
            "gateway": self.gateway,
            "catalog_model_name": self.catalog_model_name,
            "returned_model": self.returned_model,
            "model_version": self.model_version,
            "response_id": self.response_id,
            "observed_at": self.observed_at,
            "returned_provider": self.returned_provider,
            "backend_revision": self.backend_revision,
            "api_success": self.api_success,
            "http_status": self.http_status,
            "response_object_type": self.response_object_type,
            "finish_reason": self.finish_reason,
            "assistant_content_present": self.assistant_content_present,
            "assistant_content_length": self.assistant_content_length,
            "reasoning_present": self.reasoning_present,
            "reasoning_length": self.reasoning_length,
            "tool_calls_present": self.tool_calls_present,
            "usage_metadata_present": self.usage_metadata_present,
            "usage": self.usage,
            "quota": self.quota,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "retry_after_seconds": self.retry_after_seconds,
            "rate_limit_dimension": self.rate_limit_dimension,
            "structured_requested": self.structured_requested,
            "requested_output_mode": self.requested_output_mode,
            "actual_output_mode": self.actual_output_mode,
            "provider_schema_enforced": self.provider_schema_enforced,
            "local_schema_validated": self.local_schema_validated,
            "error_class": self.error_class,
            "safe_error_summary": self.safe_error_summary,
        }

    def safe_metadata_json(self) -> str:
        return json.dumps(self.safe_metadata(), ensure_ascii=False, sort_keys=True)


class JudgeProvider(Protocol):
    """Provider boundary consumed by the provider-independent judge evaluator."""

    provider_name: str
    base_url_identifier: str
    model: str
    output_mode: str

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall: ...


def _safe_usage(value: Any) -> dict[str, int | float | str] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, int | float | str] = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if isinstance(item, (bool, int, float, str)) and ("token" in lowered or "cost" in lowered):
            safe[str(key)] = item
    return safe or None


def _retry_after_seconds(response: ProviderHTTPResponse) -> float | None:
    """Read a numeric retry delay without retaining provider response text."""

    for key, header_value in response.headers.items():
        if key.casefold() == "retry-after":
            try:
                delay = float(header_value)
            except (TypeError, ValueError):
                break
            if delay >= 0:
                return delay
    details = response.body.get("error")
    details = details.get("details") if isinstance(details, Mapping) else None
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, Mapping):
                continue
            for key in ("retryDelay", "retry_after", "retryAfter"):
                detail_value = detail.get(key)
                if isinstance(detail_value, (int, float)) and detail_value >= 0:
                    return float(detail_value)
                if isinstance(detail_value, str):
                    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*s?\s*", detail_value)
                    if match:
                        return float(match.group(1))
    return None


def _rate_limit_dimension(response: ProviderHTTPResponse) -> str | None:
    """Classify only explicit quota dimension metadata; never guess silently."""

    if response.status_code != 429:
        return None
    error = response.body.get("error")
    searchable = json.dumps(error, ensure_ascii=False).casefold()
    if any(token in searchable for token in ("requestsperday", "requests_per_day", "rpd")):
        return "RPD"
    if any(token in searchable for token in ("tokensperminute", "tokens_per_minute", "tpm")):
        return "TPM"
    if any(token in searchable for token in ("requestsperminute", "requests_per_minute", "rpm")):
        return "RPM"
    return "OTHER"


def _safe_quota(value: Any) -> dict[str, int | float | str] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, int | float | str] = {}
    for key in (
        "daily_quota_tokens",
        "daily_usage_tokens",
        "daily_remaining_tokens",
    ):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item
    return safe if len(safe) == 3 else None


def _error_class(status_code: int) -> str:
    if status_code in {401, 403}:
        return "API_AUTH_ERROR"
    if status_code == 402:
        return "API_QUOTA_ERROR"
    if status_code == 429:
        return "API_RATE_LIMIT"
    if status_code in {408, 504}:
        return "API_TIMEOUT"
    if 500 <= status_code < 600:
        return "API_SERVER_ERROR"
    return "API_ERROR"


def _safe_error_summary(response: ProviderHTTPResponse) -> str | None:
    if 200 <= response.status_code < 300:
        return None
    error = response.body.get("error")
    details: dict[str, Any] = {}
    if isinstance(error, Mapping):
        for key in ("status", "type", "code"):
            value = error.get(key)
            if isinstance(value, (str, int)) and len(str(value)) <= 80:
                details[key] = value
        message = _safe_error_text(error.get("message"))
        if message is not None:
            details["message"] = message
        violations = _safe_field_violations(error.get("details"))
        if violations:
            details["field_violations"] = violations
    elif isinstance(error, str):
        candidate = error.strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", candidate) and any(
            term in candidate.casefold()
            for term in ("auth", "permission", "blocked", "quota", "rate", "invalid", "model")
        ):
            details["code"] = candidate
        else:
            details["message"] = "[REDACTED_ERROR_MESSAGE]"
    elif "message" in response.body:
        message = _safe_error_text(response.body.get("message"))
        if message is not None:
            details["message"] = message
    suffix = f" {json.dumps(details, ensure_ascii=False, sort_keys=True)}" if details else ""
    return f"Provider returned HTTP {response.status_code}.{suffix}"


def _safe_error_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = " ".join(value.split())
    lowered = text.casefold()
    if any(term in lowered for term in ("credential", "authorization", "bearer", "secret")):
        return "[REDACTED_ERROR_MESSAGE]"
    text = re.sub(
        r"(?i)(api[-_ ]?key|token)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return text[:240]


def _safe_field_violations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    violations: list[dict[str, str]] = []
    for detail in value:
        if not isinstance(detail, Mapping):
            continue
        entries = detail.get("fieldViolations")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            field = _safe_error_text(entry.get("field"))
            description = _safe_error_text(entry.get("description"))
            if field is not None or description is not None:
                violations.append(
                    {
                        key: value
                        for key, value in (("field", field), ("description", description))
                        if value is not None
                    }
                )
    return violations[:8]


def _transport_error(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "API_TIMEOUT"
    return "API_NETWORK_ERROR"


def _default_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> ProviderHTTPResponse:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS URLs
            body_bytes = response.read()
            body = json.loads(body_bytes.decode("utf-8"))
            return ProviderHTTPResponse(
                status_code=response.status,
                body=body if isinstance(body, dict) else {},
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        return ProviderHTTPResponse(
            status_code=error.code,
            body=body if isinstance(body, dict) else {},
            headers=dict(error.headers.items()) if error.headers else {},
        )
    except (OSError, URLError, TimeoutError) as error:
        raise RuntimeError(_transport_error(error)) from error


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(part.get("text", ""))
            for part in value
            if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        )
    return ""


def _default_ollama_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> ProviderHTTPResponse:
    """Call only the local Ollama HTTP boundary and classify transport failures safely."""

    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - loopback URL
            body_bytes = response.read()
            body = json.loads(body_bytes.decode("utf-8"))
            return ProviderHTTPResponse(
                status_code=response.status,
                body=body if isinstance(body, dict) else {},
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        return ProviderHTTPResponse(
            status_code=error.code,
            body=body if isinstance(body, dict) else {},
            headers=dict(error.headers.items()) if error.headers else {},
        )
    except TimeoutError as error:
        raise RuntimeError("LOCAL_TIMEOUT") from error
    except (OSError, URLError) as error:
        raise RuntimeError("LOCAL_CONNECTION_ERROR") from error


def _ollama_usage(body: Mapping[str, Any]) -> dict[str, int | float | str] | None:
    """Project Ollama counters to safe token/timing metadata without response text."""

    aliases = {
        "prompt_eval_count": "prompt_tokens",
        "eval_count": "completion_tokens",
        "total_duration": "total_duration_ns",
        "load_duration": "load_duration_ns",
        "prompt_eval_duration": "prompt_eval_duration_ns",
        "eval_duration": "eval_duration_ns",
    }
    usage: dict[str, int | float | str] = {}
    for source, target in aliases.items():
        value = body.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            usage[target] = value
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if isinstance(prompt_tokens, (int, float)) and isinstance(completion_tokens, (int, float)):
        usage["total_tokens"] = prompt_tokens + completion_tokens
    eval_duration = usage.get("eval_duration_ns")
    if isinstance(completion_tokens, (int, float)) and isinstance(eval_duration, (int, float)):
        if eval_duration > 0:
            usage["tokens_per_second"] = completion_tokens / (eval_duration / 1_000_000_000)
    return usage or None


def _local_error_class(response: ProviderHTTPResponse) -> str:
    """Classify local service failures without persisting the local error body."""

    searchable = json.dumps(response.body, ensure_ascii=False).casefold()
    if any(term in searchable for term in ("out of memory", "outofmemory", "oom")):
        return "LOCAL_OOM"
    if any(
        term in searchable
        for term in ("failed to load", "insufficient memory", "resource exhausted")
    ):
        return "LOCAL_RESOURCE_ERROR"
    if response.status_code == 404:
        return "LOCAL_MODEL_NOT_FOUND"
    if response.status_code in {408, 504}:
        return "LOCAL_TIMEOUT"
    if 500 <= response.status_code < 600:
        return "LOCAL_SERVER_ERROR"
    return "LOCAL_REQUEST_ERROR"


def _local_error_summary(response: ProviderHTTPResponse, error_class: str) -> str:
    return f"Ollama local request failed with {error_class} (HTTP {response.status_code})."


def _common_call(
    *,
    provider: str,
    requested_model: str,
    response: ProviderHTTPResponse,
    latency_ms: float,
    content: str,
    returned_model: str | None,
    response_object_type: str | None,
    finish_reason: str | None,
    reasoning_present: bool,
    reasoning_length: int,
    tool_calls_present: bool,
    output_mode: JudgeOutputMode,
    provider_schema_enforced: bool,
    structured_requested: bool,
    gateway: str | None = None,
    catalog_model_name: str | None = None,
    returned_provider: str | None = None,
    backend_revision: str | None = None,
    quota: dict[str, int | float | str] | None = None,
    model_version: str | None = None,
    response_id: str | None = None,
    observed_at: str | None = None,
) -> ProviderCall:
    usage = _safe_usage(response.body.get("usage") or response.body.get("usageMetadata"))
    api_success = 200 <= response.status_code < 300
    return ProviderCall(
        provider=provider,
        requested_model=requested_model,
        gateway=gateway,
        catalog_model_name=catalog_model_name,
        returned_model=returned_model,
        model_version=model_version,
        response_id=response_id,
        observed_at=observed_at or datetime.now(UTC).isoformat(),
        returned_provider=returned_provider,
        backend_revision=backend_revision,
        api_success=api_success,
        http_status=response.status_code,
        response_object_type=response_object_type,
        finish_reason=finish_reason,
        assistant_content=content or None,
        assistant_content_present=bool(content.strip()),
        assistant_content_length=len(content),
        reasoning_present=reasoning_present,
        reasoning_length=reasoning_length,
        tool_calls_present=tool_calls_present,
        usage_metadata_present=usage is not None,
        usage=usage,
        quota=quota,
        request_id=response.headers.get("x-request-id"),
        latency_ms=latency_ms,
        retry_after_seconds=_retry_after_seconds(response),
        rate_limit_dimension=_rate_limit_dimension(response),
        structured_requested=structured_requested,
        requested_output_mode=output_mode,
        actual_output_mode=output_mode,
        provider_schema_enforced=provider_schema_enforced,
        local_schema_validated=True,
        error_class=None if api_success else _error_class(response.status_code),
        safe_error_summary=_safe_error_summary(response),
    )


class _BaseProviderAdapter:
    provider_name: str
    base_url_identifier: str
    model: str

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        transport: Transport | None = None,
        timeout_seconds: float = 60.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_SCHEMA_STRICT,
    ) -> None:
        if not api_key.strip():
            raise ValueError("provider API key must not be empty")
        self._api_key = api_key
        self.model = model
        self.output_mode = JudgeOutputMode(output_mode)
        self._transport = transport or _default_transport
        self._timeout_seconds = timeout_seconds

    def _send(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> ProviderHTTPResponse:
        try:
            return self._transport(url, headers, payload, self._timeout_seconds)
        except RuntimeError as error:
            error_class = str(error)
            if error_class not in {"API_TIMEOUT", "API_NETWORK_ERROR"}:
                error_class = "API_NETWORK_ERROR"
            raise RuntimeError(error_class) from error

    def _failed_call(self, error_class: str, *, latency_ms: float | None = None) -> ProviderCall:
        return ProviderCall(
            provider=self.provider_name,
            requested_model=self.model,
            gateway=getattr(self, "gateway", None),
            catalog_model_name=getattr(self, "catalog_model_name", None),
            backend_revision=getattr(self, "backend_revision", None),
            latency_ms=latency_ms,
            structured_requested=self.output_mode is not JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
            requested_output_mode=self.output_mode,
            actual_output_mode=self.output_mode,
            provider_schema_enforced=self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT,
            local_schema_validated=True,
            observed_at=datetime.now(UTC).isoformat(),
            error_class=error_class,
            safe_error_summary="Provider request did not return a usable completion.",
        )


class OllamaProviderAdapter:
    """Local Ollama chat adapter using structured JSON plus local validation."""

    provider_name = "local-ollama"
    base_url_identifier = "127.0.0.1:11434/api/chat"
    gateway = "Ollama local service"
    routing_immutable = True
    provider_family = "Local Ollama"

    def __init__(
        self,
        *,
        model: str = "qwen3:8b",
        transport: Transport | None = None,
        timeout_seconds: float = 300.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_SCHEMA_STRICT,
        model_digest: str | None = None,
        quantization: str | None = None,
        parameter_size: str | None = None,
        context_length: int | None = None,
        inference_device: str = "cpu",
        thinking_mode: str = "OFF",
        ollama_version: str | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("local Ollama model must not be empty")
        if inference_device not in {"cpu", "gpu", "auto"}:
            raise ValueError("local Ollama inference_device must be cpu, gpu, or auto")
        if thinking_mode not in {"ON", "OFF", "UNAVAILABLE"}:
            raise ValueError("local Ollama thinking_mode must be ON, OFF, or UNAVAILABLE")
        self.model = model
        self.output_mode = JudgeOutputMode(output_mode)
        self._transport = transport or _default_ollama_transport
        self._timeout_seconds = timeout_seconds
        self.model_digest = model_digest
        self.quantization = quantization
        self.parameter_size = parameter_size
        self.context_length = context_length
        self.inference_device = inference_device
        self.thinking_mode = thinking_mode
        self.ollama_version = ollama_version

    def _failed_call(self, error_class: str) -> ProviderCall:
        return ProviderCall(
            provider=self.provider_name,
            requested_model=self.model,
            gateway=self.gateway,
            backend_revision=self.model_digest,
            observed_at=datetime.now(UTC).isoformat(),
            structured_requested=self.output_mode
            in {
                JudgeOutputMode.JSON_SCHEMA_STRICT,
                JudgeOutputMode.JSON_SCHEMA_BEST_EFFORT,
            },
            requested_output_mode=self.output_mode,
            actual_output_mode=self.output_mode,
            provider_schema_enforced=self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT,
            local_schema_validated=True,
            error_class=error_class,
            safe_error_summary="Ollama local request did not return a usable completion.",
        )

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "top_p": config.top_p,
                "num_predict": config.max_output_tokens,
            },
        }
        structured_requested = False
        provider_schema_enforced = False
        if self.output_mode in {
            JudgeOutputMode.JSON_SCHEMA_STRICT,
            JudgeOutputMode.JSON_SCHEMA_BEST_EFFORT,
        }:
            payload["format"] = dict(schema)
            structured_requested = True
            provider_schema_enforced = self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT
        elif self.output_mode is JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION:
            payload["format"] = "json"
            structured_requested = True
        if config.include_reasoning is False:
            payload["think"] = False
        started = time.perf_counter()
        try:
            response = self._transport(
                "http://127.0.0.1:11434/api/chat",
                {"Content-Type": "application/json"},
                payload,
                self._timeout_seconds,
            )
        except RuntimeError as error:
            return self._failed_call(str(error))
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        body = response.body
        message = body.get("message", {})
        message = message if isinstance(message, Mapping) else {}
        content = _content_text(message.get("content"))
        thinking = message.get("thinking")
        usage = _ollama_usage(body)
        returned_model = body.get("model")
        returned_model = str(returned_model) if returned_model else None
        call = ProviderCall(
            provider=self.provider_name,
            requested_model=self.model,
            gateway=self.gateway,
            backend_revision=self.model_digest,
            returned_model=returned_model,
            model_version=self.model_digest,
            observed_at=(str(body["created_at"]) if body.get("created_at") else None),
            api_success=200 <= response.status_code < 300,
            http_status=response.status_code,
            response_object_type="chat",
            finish_reason=(str(body["done_reason"]) if body.get("done_reason") else None),
            assistant_content=content or None,
            assistant_content_present=bool(content.strip()),
            assistant_content_length=len(content),
            reasoning_present=isinstance(thinking, str) and bool(thinking),
            reasoning_length=(len(thinking) if isinstance(thinking, str) else 0),
            usage_metadata_present=usage is not None,
            usage=usage,
            request_id=(str(body["id"]) if body.get("id") else None),
            latency_ms=latency_ms,
            structured_requested=structured_requested,
            requested_output_mode=self.output_mode,
            actual_output_mode=self.output_mode,
            provider_schema_enforced=provider_schema_enforced,
            local_schema_validated=True,
            error_class=(
                None if 200 <= response.status_code < 300 else _local_error_class(response)
            ),
            safe_error_summary=(
                None
                if 200 <= response.status_code < 300
                else _local_error_summary(response, _local_error_class(response))
            ),
        )
        if call.api_success and returned_model != self.model:
            return replace(
                call,
                api_success=False,
                assistant_content=None,
                assistant_content_present=False,
                assistant_content_length=0,
                error_class="LOCAL_MODEL_MISMATCH",
                safe_error_summary="Ollama returned a different model than requested.",
            )
        return call


class GeminiProviderAdapter(_BaseProviderAdapter):
    """Gemini native generateContent adapter with structured JSON output."""

    provider_name = "gemini"
    base_url_identifier = "generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash-lite",
        transport: Transport | None = None,
        timeout_seconds: float = 60.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_SCHEMA_STRICT,
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        generation_config: dict[str, Any] = {
            "temperature": config.temperature,
            "topP": config.top_p,
            "maxOutputTokens": config.max_output_tokens,
        }
        if self.output_mode in {
            JudgeOutputMode.JSON_SCHEMA_STRICT,
            JudgeOutputMode.JSON_SCHEMA_BEST_EFFORT,
        }:
            generation_config.update(
                {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": dict(schema),
                }
            )
        elif self.output_mode is JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION:
            generation_config["responseMimeType"] = "application/json"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        try:
            started = time.perf_counter()
            response = self._send(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                {"Content-Type": "application/json", "x-goog-api-key": self._api_key},
                payload,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except RuntimeError as error:
            return self._failed_call(str(error))
        candidate = response.body.get("candidates", [{}])[0]
        candidate = candidate if isinstance(candidate, Mapping) else {}
        content_payload = candidate.get("content", {})
        parts = content_payload.get("parts", []) if isinstance(content_payload, Mapping) else []
        content = _content_text(parts)
        reasoning_values = [
            part for part in parts if isinstance(part, Mapping) and part.get("thought")
        ]
        usage = response.body.get("usageMetadata")
        normalized_body = dict(response.body)
        normalized_body["usage"] = usage
        normalized_response = ProviderHTTPResponse(
            response.status_code, normalized_body, response.headers
        )
        return _common_call(
            provider=self.provider_name,
            requested_model=self.model,
            response=normalized_response,
            latency_ms=latency_ms,
            content=content,
            returned_model=(self.model),
            model_version=(
                str(response.body["modelVersion"])
                if response.body.get("modelVersion") is not None
                else None
            ),
            response_id=(
                str(response.body["responseId"])
                if response.body.get("responseId") is not None
                else None
            ),
            response_object_type="generateContent",
            finish_reason=(
                str(candidate["finishReason"]) if candidate.get("finishReason") else None
            ),
            reasoning_present=bool(reasoning_values),
            reasoning_length=sum(
                len(json.dumps(value, ensure_ascii=False)) for value in reasoning_values
            ),
            tool_calls_present=False,
            output_mode=self.output_mode,
            provider_schema_enforced=self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT,
            structured_requested=self.output_mode is not JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
        )


class GroqProviderAdapter(_BaseProviderAdapter):
    """Groq OpenAI-compatible adapter for GPT-OSS strict structured output."""

    provider_name = "groq"
    base_url_identifier = "api.groq.com/openai/v1"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "openai/gpt-oss-20b",
        transport: Transport | None = None,
        timeout_seconds: float = 60.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_SCHEMA_STRICT,
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_completion_tokens": config.max_output_tokens,
            "stream": False,
            "include_reasoning": config.include_reasoning,
            "reasoning_effort": config.reasoning_effort,
        }
        if self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ragtruth_strict_groundedness",
                    "strict": True,
                    "schema": dict(schema),
                },
            }
        elif self.output_mode is JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION:
            payload["response_format"] = {"type": "json_object"}
        try:
            started = time.perf_counter()
            response = self._send(
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                payload,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except RuntimeError as error:
            return self._failed_call(str(error))
        choices = response.body.get("choices", [])
        choice = choices[0] if isinstance(choices, list) and choices else {}
        choice = choice if isinstance(choice, Mapping) else {}
        message = choice.get("message", {})
        message = message if isinstance(message, Mapping) else {}
        content = _content_text(message.get("content"))
        reasoning = message.get("reasoning", message.get("reasoning_content"))
        tool_calls = message.get("tool_calls")
        return _common_call(
            provider=self.provider_name,
            requested_model=self.model,
            response=response,
            latency_ms=latency_ms,
            content=content,
            returned_model=(str(response.body["model"]) if response.body.get("model") else None),
            response_object_type=(
                str(response.body["object"]) if response.body.get("object") else None
            ),
            finish_reason=(str(choice["finish_reason"]) if choice.get("finish_reason") else None),
            reasoning_present=reasoning is not None,
            reasoning_length=(
                len(json.dumps(reasoning, ensure_ascii=False)) if reasoning is not None else 0
            ),
            tool_calls_present=isinstance(tool_calls, list) and bool(tool_calls),
            output_mode=self.output_mode,
            provider_schema_enforced=self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT,
            structured_requested=self.output_mode is not JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
        )


class OpenRouterProviderAdapter(_BaseProviderAdapter):
    """Explicitly non-immutable OpenRouter fallback adapter."""

    provider_name = "openrouter"
    base_url_identifier = "openrouter.ai/api/v1"
    routing_immutable = False

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "liquid/lfm-2.5-2.6b:free",
        transport: Transport | None = None,
        timeout_seconds: float = 60.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION,
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_output_tokens,
            "stream": False,
        }
        if self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ragtruth_strict_groundedness",
                    "strict": True,
                    "schema": dict(schema),
                },
            }
        elif self.output_mode is JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION:
            payload["response_format"] = {"type": "json_object"}
        try:
            started = time.perf_counter()
            response = self._send(
                "https://openrouter.ai/api/v1/chat/completions",
                {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                payload,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except RuntimeError as error:
            return self._failed_call(str(error))
        choices = response.body.get("choices", [])
        choice = choices[0] if isinstance(choices, list) and choices else {}
        choice = choice if isinstance(choice, Mapping) else {}
        message = choice.get("message", {})
        message = message if isinstance(message, Mapping) else {}
        content = _content_text(message.get("content"))
        reasoning = message.get("reasoning", message.get("reasoning_content"))
        tool_calls = message.get("tool_calls")
        return _common_call(
            provider=self.provider_name,
            requested_model=self.model,
            response=response,
            latency_ms=latency_ms,
            content=content,
            returned_model=(str(response.body["model"]) if response.body.get("model") else None),
            response_object_type=(
                str(response.body["object"]) if response.body.get("object") else None
            ),
            finish_reason=(str(choice["finish_reason"]) if choice.get("finish_reason") else None),
            reasoning_present=reasoning is not None,
            reasoning_length=(
                len(json.dumps(reasoning, ensure_ascii=False)) if reasoning is not None else 0
            ),
            tool_calls_present=isinstance(tool_calls, list) and bool(tool_calls),
            output_mode=self.output_mode,
            provider_schema_enforced=self.output_mode is JudgeOutputMode.JSON_SCHEMA_STRICT,
            structured_requested=self.output_mode is not JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
        )


class OKMDProviderAdapter(_BaseProviderAdapter):
    """OKMD gateway adapter using plain JSON text plus generic local validation."""

    provider_name = "okmd"
    gateway = "OKMD AI Playground"
    base_url_identifier = "gen.ai.kku.ac.th/okmd/api/v1"
    backend_revision = "unavailable"
    routing_immutable = False

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "unavailable",
        catalog_model_name: str = "unavailable",
        transport: Transport | None = None,
        timeout_seconds: float = 60.0,
        output_mode: JudgeOutputMode | str = JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )
        self.catalog_model_name = catalog_model_name

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        del schema
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.temperature,
            "max_tokens": config.max_output_tokens,
            "stream": False,
        }
        try:
            started = time.perf_counter()
            response = self._send(
                "https://gen.ai.kku.ac.th/okmd/api/v1/chat/completions",
                {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                payload,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except RuntimeError as error:
            return self._failed_call(str(error))
        choices = response.body.get("choices", [])
        choice = choices[0] if isinstance(choices, list) and choices else {}
        choice = choice if isinstance(choice, Mapping) else {}
        message = choice.get("message", {})
        message = message if isinstance(message, Mapping) else {}
        content = _content_text(message.get("content"))
        returned_model = response.body.get("model")
        returned_provider = next(
            (
                response.body.get(key)
                for key in ("provider", "backend", "model_provider")
                if isinstance(response.body.get(key), str)
            ),
            None,
        )
        backend_revision = next(
            (
                response.body.get(key)
                for key in ("backend_revision", "backendRevision", "revision")
                if isinstance(response.body.get(key), str)
            ),
            self.backend_revision,
        )
        return _common_call(
            provider=self.provider_name,
            requested_model=self.model,
            response=response,
            latency_ms=latency_ms,
            content=content,
            returned_model=str(returned_model) if returned_model else self.model,
            response_object_type=(
                str(response.body["object"]) if response.body.get("object") else None
            ),
            finish_reason=(str(choice["finish_reason"]) if choice.get("finish_reason") else None),
            reasoning_present=False,
            reasoning_length=0,
            tool_calls_present=False,
            output_mode=self.output_mode,
            provider_schema_enforced=False,
            structured_requested=False,
            gateway=self.gateway,
            catalog_model_name=self.catalog_model_name,
            returned_provider=str(returned_provider) if returned_provider else None,
            backend_revision=str(backend_revision) if backend_revision else self.backend_revision,
            quota=_safe_quota(response.body.get("model_quota")),
        )
