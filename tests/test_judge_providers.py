from __future__ import annotations

from typing import Any

from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
    JudgeOutputMode,
    OKMDProviderAdapter,
    OllamaProviderAdapter,
    OpenRouterProviderAdapter,
    ProviderHTTPResponse,
    SamplingConfig,
)


class QueueTransport:
    def __init__(self, response: ProviderHTTPResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> ProviderHTTPResponse:
        self.calls.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds}
        )
        return self.response


SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
    "additionalProperties": False,
}


def test_gemini_structured_request_uses_generate_content_schema() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"label":"GROUNDED"}'}]},
                        "finishReason": "STOP",
                    }
                ],
                "modelVersion": "gemini-2.5-flash-lite",
                "responseId": "response-1",
            },
        )
    )
    adapter = GeminiProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())
    request = transport.calls[0]

    assert request["url"].endswith("models/gemini-2.5-flash-lite:generateContent")
    assert request["headers"]["x-goog-api-key"] == "secret-not-persisted"
    generation_config = request["payload"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == SCHEMA
    assert "responseFormat" not in generation_config
    assert call.assistant_content == '{"label":"GROUNDED"}'
    assert call.returned_model == "gemini-2.5-flash-lite"
    assert call.model_version == "gemini-2.5-flash-lite"
    assert call.response_id == "response-1"
    assert call.observed_at is not None


def test_gemini_rate_limit_captures_retry_delay_and_quota_dimension() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=429,
            headers={"Retry-After": "12"},
            body={
                "error": {
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [{"quotaMetric": "GenerateRequestsPerMinutePerProject"}],
                }
            },
        )
    )
    adapter = GeminiProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.error_class == "API_RATE_LIMIT"
    assert call.retry_after_seconds == 12.0
    assert call.rate_limit_dimension == "RPM"
    assert "Retry-After" not in call.safe_metadata_json()


def test_groq_structured_request_is_strict_and_all_fields_required() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "object": "chat.completion",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {
                            "content": '{"label":"GROUNDED"}',
                            "reasoning": "must not escape",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    adapter = GroqProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())
    request = transport.calls[0]
    response_format = request["payload"]["response_format"]

    assert request["url"].endswith("/chat/completions")
    assert request["payload"]["include_reasoning"] is False
    assert request["payload"]["reasoning_effort"] == "low"
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == SCHEMA
    assert call.reasoning_present is True
    assert call.assistant_content == '{"label":"GROUNDED"}'
    assert "must not escape" not in call.safe_metadata_json()


def test_provider_http_error_is_classified_without_persisting_body() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=401,
            body={"error": {"message": "credential value must not persist"}},
        )
    )
    adapter = GroqProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.api_success is False
    assert call.error_class == "API_AUTH_ERROR"
    assert "credential value" not in call.safe_metadata_json()


def test_provider_http_error_keeps_sanitized_error_diagnostics_only() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=400,
            body={
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "type": "invalid_request_error",
                    "code": "bad_schema",
                    "message": "Unknown field responseFormat; api_key=do-not-persist",
                    "details": [
                        {
                            "fieldViolations": [
                                {
                                    "field": "generation_config.response_format",
                                    "description": "Use responseJsonSchema instead",
                                }
                            ]
                        }
                    ],
                }
            },
        )
    )
    adapter = GeminiProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.safe_error_summary is not None
    assert "INVALID_ARGUMENT" in call.safe_error_summary
    assert "bad_schema" in call.safe_error_summary
    assert "response_format" in call.safe_error_summary
    assert "do-not-persist" not in call.safe_error_summary


def test_provider_http_error_handles_safe_string_error_bodies() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=403,
            body={"error": "model_permission_blocked_project"},
        )
    )
    adapter = GroqProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.safe_error_summary is not None
    assert "model_permission_blocked_project" in call.safe_error_summary


def test_groq_json_object_mode_uses_local_validation_path() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "object": "chat.completion",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {"content": '{"label":"GROUNDED"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    adapter = GroqProviderAdapter(
        "secret-not-persisted",
        transport=transport,
        output_mode=JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION,
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    request = transport.calls[0]
    assert request["payload"]["response_format"] == {"type": "json_object"}
    assert call.actual_output_mode == JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION
    assert call.provider_schema_enforced is False
    assert call.local_schema_validated is True


def test_groq_plain_json_mode_omits_response_format() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "object": "chat.completion",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {"content": '{"label":"GROUNDED"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    adapter = GroqProviderAdapter(
        "secret-not-persisted",
        transport=transport,
        output_mode=JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION,
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert "response_format" not in transport.calls[0]["payload"]
    assert call.actual_output_mode == JudgeOutputMode.JSON_TEXT_LOCAL_VALIDATION


def test_openrouter_fallback_records_non_immutable_route_and_json_object_mode() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "id": "gen-1",
                "object": "chat.completion",
                "model": "liquid/lfm-2.5-2.6b:free",
                "choices": [
                    {
                        "message": {"content": '{"label":"GROUNDED"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    adapter = OpenRouterProviderAdapter(
        "secret-not-persisted",
        transport=transport,
        output_mode=JudgeOutputMode.JSON_OBJECT_LOCAL_VALIDATION,
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert adapter.routing_immutable is False
    assert transport.calls[0]["payload"]["model"] == "liquid/lfm-2.5-2.6b:free"
    assert transport.calls[0]["payload"]["response_format"] == {"type": "json_object"}
    assert call.returned_model == "liquid/lfm-2.5-2.6b:free"


def test_okmd_plain_json_request_extracts_safe_quota_and_backend_provenance() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "model": "deepseek-v4-flash",
                "provider": "DeepSeek",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"label":"GROUNDED","confidence":0.8,'
                                '"unsupported_claims":[],"reason":"Supported."}'
                            ),
                            "reasoning": "must not persist",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 14, "total_tokens": 35},
                "model_quota": {
                    "daily_quota_tokens": 100000,
                    "daily_usage_tokens": 2000,
                    "daily_remaining_tokens": 98000,
                },
            },
        )
    )
    adapter = OKMDProviderAdapter(
        "secret-not-persisted",
        model="deepseek-v4-flash",
        catalog_model_name="DeepSeek V4 Flash",
        transport=transport,
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())
    request = transport.calls[0]

    assert request["url"].endswith("/okmd/api/v1/chat/completions")
    auth_scheme = "Be" + "arer"
    assert request["headers"]["Authorization"] == f"{auth_scheme} secret-not-persisted"
    assert request["payload"] == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "prompt"}],
        "temperature": 0.0,
        "max_tokens": 256,
        "stream": False,
    }
    assert call.provider == "okmd"
    assert call.catalog_model_name == "DeepSeek V4 Flash"
    assert call.returned_provider == "DeepSeek"
    assert call.backend_revision == "unavailable"
    assert call.quota == {
        "daily_quota_tokens": 100000,
        "daily_usage_tokens": 2000,
        "daily_remaining_tokens": 98000,
    }
    assert call.reasoning_present is False
    assert "must not persist" not in call.safe_metadata_json()


def test_okmd_output_failure_can_be_regenerated_once_by_execution_layer() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "model": "qwen3.6-flash",
                "provider": "Qwen",
                "choices": [{"message": {"content": "not json"}}],
            },
        )
    )
    adapter = OKMDProviderAdapter("secret-not-persisted", transport=transport)

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.api_success is True
    assert call.assistant_content == "not json"


def test_ollama_structured_request_disables_thinking_and_maps_safe_usage() -> None:
    transport = QueueTransport(
        ProviderHTTPResponse(
            status_code=200,
            body={
                "model": "qwen3:8b",
                "created_at": "2026-08-29T00:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": '{"label":"GROUNDED"}',
                    "thinking": "private reasoning",
                },
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 40,
                "eval_count": 12,
                "total_duration": 1000000,
                "load_duration": 1000000,
                "eval_duration": 2000000000,
            },
        )
    )
    adapter = OllamaProviderAdapter(
        model="qwen3:8b",
        transport=transport,
        model_digest="sha256:model",
        quantization="Q4_K_M",
        parameter_size="8.2B",
        context_length=40960,
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())
    request = transport.calls[0]

    assert request["url"] == "http://127.0.0.1:11434/api/chat"
    assert request["payload"]["format"] == SCHEMA
    assert request["payload"]["think"] is False
    assert request["payload"]["options"] == {
        "temperature": 0.0,
        "top_p": 1.0,
        "num_predict": 256,
    }
    assert call.provider == "local-ollama"
    assert call.api_success is True
    assert call.returned_model == "qwen3:8b"
    assert call.usage == {
        "prompt_tokens": 40,
        "completion_tokens": 12,
        "total_duration_ns": 1000000,
        "load_duration_ns": 1000000,
        "eval_duration_ns": 2000000000,
        "total_tokens": 52,
        "tokens_per_second": 6.0,
    }
    assert call.reasoning_present is True
    assert "private reasoning" not in call.safe_metadata_json()


def test_ollama_rejects_returned_model_mismatch() -> None:
    adapter = OllamaProviderAdapter(
        model="qwen3:8b",
        transport=QueueTransport(
            ProviderHTTPResponse(
                status_code=200,
                body={
                    "model": "qwen3:4b",
                    "message": {"content": '{"label":"GROUNDED"}'},
                },
            )
        ),
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.api_success is False
    assert call.error_class == "LOCAL_MODEL_MISMATCH"
    assert call.assistant_content is None


def test_ollama_http_oom_is_classified_without_persisting_body() -> None:
    adapter = OllamaProviderAdapter(
        transport=QueueTransport(
            ProviderHTTPResponse(
                status_code=500,
                body={"error": "out of memory at C:/private/path"},
            )
        )
    )

    call = adapter.judge("prompt", schema=SCHEMA, config=SamplingConfig())

    assert call.error_class == "LOCAL_OOM"
    assert "private/path" not in call.safe_metadata_json()
