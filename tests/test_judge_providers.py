from __future__ import annotations

from typing import Any

from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
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
    assert generation_config["responseFormat"] == {
        "text": {"mimeType": "application/json", "schema": SCHEMA}
    }
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
