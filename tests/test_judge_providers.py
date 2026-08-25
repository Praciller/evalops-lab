from __future__ import annotations

from typing import Any

from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
    JudgeOutputMode,
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
