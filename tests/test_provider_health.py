from __future__ import annotations

from evalops.providers.health import (
    ProviderHealthResult,
    assess_completion_response,
    classify_http_status,
    model_diversity_ready,
    select_openrouter_model,
)


def _chat_payload(content: object, **message_fields: object) -> dict[str, object]:
    message = {"role": "assistant", "content": content, **message_fields}
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "openai/gpt-oss-20b",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
    }


def test_exact_sentinel_is_completion_and_instruction_pass() -> None:
    result = assess_completion_response(_chat_payload("EVALOPS_OK"))

    assert result.completion_status == "PASS"
    assert result.instruction_adherence_status == "PASS"
    assert result.assistant_content_present is True
    assert result.assistant_content_length == 10


def test_extra_content_is_partial_instruction_adherence_not_connectivity_failure() -> None:
    result = assess_completion_response(_chat_payload("EVALOPS_OK — ready."))

    assert result.completion_status == "PASS"
    assert result.instruction_adherence_status == "PARTIAL"


def test_reasoning_is_diagnostic_but_final_content_drives_completion() -> None:
    result = assess_completion_response(
        _chat_payload("EVALOPS_OK", reasoning="private reasoning must not be persisted")
    )

    assert result.completion_status == "PASS"
    assert result.instruction_adherence_status == "PASS"
    assert result.reasoning_present is True
    assert result.reasoning_length == len("private reasoning must not be persisted")
    assert "private reasoning" not in result.model_dump_json()


def test_reasoning_without_final_content_is_invalid_response() -> None:
    result = assess_completion_response(
        _chat_payload(None, reasoning="reasoning only", reasoning_content="still not final")
    )

    assert result.completion_status == "INVALID_RESPONSE"
    assert result.instruction_adherence_status == "FAIL"
    assert result.assistant_content_present is False
    assert result.reasoning_present is True


def test_valid_structured_json_is_checked_separately() -> None:
    result = assess_completion_response(
        _chat_payload('{"status":"EVALOPS_OK"}'),
        structured_schema={"status": "EVALOPS_OK"},
    )

    assert result.completion_status == "PASS"
    assert result.structured_output_status == "PASS"
    assert result.structured_parse_success is True


def test_invalid_structured_json_does_not_invalidate_completion() -> None:
    result = assess_completion_response(
        _chat_payload("not-json"), structured_schema={"status": "EVALOPS_OK"}
    )

    assert result.completion_status == "PASS"
    assert result.structured_output_status == "PARSE_FAILED"
    assert result.structured_parse_success is False


def test_http_error_classes_are_specific() -> None:
    assert classify_http_status(401, phase="auth") == "AUTH_FAILED"
    assert classify_http_status(402, phase="completion") == "QUOTA_EXHAUSTED"
    assert classify_http_status(429, phase="completion") == "RATE_LIMITED"
    assert classify_http_status(404, phase="completion") == "MODEL_UNAVAILABLE"
    assert classify_http_status(504, phase="completion") == "NETWORK_FAILED"
    assert classify_http_status(0, phase="timeout") == "NETWORK_FAILED"


def test_openrouter_selection_is_deterministic_and_prefers_structured_free_model() -> None:
    models = [
        {
            "id": "zeta/free-model:free",
            "architecture": {"modality": "text->text"},
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["temperature"],
        },
        {
            "id": "alpha/free-model:free",
            "architecture": {"modality": "text->text"},
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["response_format", "temperature", "seed"],
        },
        {
            "id": "vision/free-model:free",
            "architecture": {"modality": "image->text"},
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["response_format"],
        },
    ]

    assert select_openrouter_model(models) == "alpha/free-model:free"


def test_policy_blocked_provider_remains_ineligible() -> None:
    result = ProviderHealthResult(
        provider="thaillm",
        authentication_status="PASS",
        discovery_status="PASS",
        connectivity_status="PASS",
        completion_status="PASS",
        instruction_adherence_status="PARTIAL",
        benchmark_eligible=False,
        benchmark_block_reason="POLICY_REVIEW_REQUIRED",
    )

    assert result.benchmark_eligible is False
    assert result.benchmark_block_reason == "POLICY_REVIEW_REQUIRED"


def test_same_underlying_model_does_not_count_as_model_diversity() -> None:
    gemini = ProviderHealthResult(
        provider="gemini",
        selected_model="gemini-2.5-flash-lite",
        authentication_status="PASS",
        discovery_status="PASS",
        connectivity_status="PASS",
        completion_status="PASS",
        benchmark_eligible=True,
    )
    okmd = ProviderHealthResult(
        provider="okmd",
        selected_model="gemini-2.5-flash-lite",
        returned_model="gemini-2.5-flash-lite",
        backend_provider="gemini",
        authentication_status="PASS",
        discovery_status="PASS",
        connectivity_status="PASS",
        completion_status="PASS",
        benchmark_eligible=True,
    )
    groq = ProviderHealthResult(
        provider="groq",
        selected_model="openai/gpt-oss-20b",
        authentication_status="PASS",
        discovery_status="PASS",
        connectivity_status="PASS",
        completion_status="PASS",
        benchmark_eligible=True,
    )

    assert model_diversity_ready([gemini, okmd]) is False
    assert model_diversity_ready([gemini, groq]) is True
