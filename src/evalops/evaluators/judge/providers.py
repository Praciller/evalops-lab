"""Provider adapters for structured strict-groundedness judge calls."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class ProviderCall:
    """In-memory call result whose safe projection excludes content and reasoning."""

    provider: str
    requested_model: str
    returned_model: str | None = None
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
    request_id: str | None = None
    latency_ms: float | None = None
    structured_requested: bool = True
    error_class: str | None = None
    safe_error_summary: str | None = None

    def safe_metadata(self) -> dict[str, Any]:
        """Return persistable metadata without final content or reasoning text."""

        return {
            "provider": self.provider,
            "requested_model": self.requested_model,
            "returned_model": self.returned_model,
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
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "structured_requested": self.structured_requested,
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
            status_code=error.code, body=body if isinstance(body, dict) else {}
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
) -> ProviderCall:
    usage = _safe_usage(response.body.get("usage") or response.body.get("usageMetadata"))
    api_success = 200 <= response.status_code < 300
    return ProviderCall(
        provider=provider,
        requested_model=requested_model,
        returned_model=returned_model,
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
        request_id=response.headers.get("x-request-id"),
        latency_ms=latency_ms,
        error_class=None if api_success else _error_class(response.status_code),
        safe_error_summary=(
            None if api_success else f"Provider returned HTTP {response.status_code}."
        ),
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
    ) -> None:
        if not api_key.strip():
            raise ValueError("provider API key must not be empty")
        self._api_key = api_key
        self.model = model
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
            latency_ms=latency_ms,
            structured_requested=True,
            error_class=error_class,
            safe_error_summary="Provider request did not return a usable completion.",
        )


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
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )

    def judge(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
        config: SamplingConfig,
    ) -> ProviderCall:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": config.temperature,
                "topP": config.top_p,
                "maxOutputTokens": config.max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
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
            returned_model=(
                str(response.body["modelVersion"])
                if response.body.get("modelVersion") is not None
                else self.model
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
    ) -> None:
        super().__init__(
            api_key,
            model=model,
            transport=transport,
            timeout_seconds=timeout_seconds,
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
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ragtruth_strict_groundedness",
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
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
        )
