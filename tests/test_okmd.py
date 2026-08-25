from __future__ import annotations

from typing import Any

import pytest

from evalops.providers.okmd import (
    OKMDClient,
    OKMDModel,
    OKMDQuota,
    estimate_pilot_tokens,
    model_family,
    parse_models_response,
    select_okmd_candidates,
    validate_quota_gate,
)


class QueueTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> Any:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout_seconds,
            }
        )
        from evalops.evaluators.judge.providers import ProviderHTTPResponse

        return ProviderHTTPResponse(status_code=200, body=self.responses.pop(0))


def test_okmd_model_discovery_uses_chat_models_list_once_and_maps_id_name() -> None:
    transport = QueueTransport(
        [{"data": [{"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash"}]}]
    )
    client = OKMDClient("secret-not-persisted", transport=transport)

    models = client.discover_models()

    assert models == [OKMDModel(model_id="deepseek-v4-flash", name="DeepSeek V4 Flash")]
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"].endswith("/okmd/api/v1/chat/models-list")
    assert transport.calls[0]["payload"] is None


def test_okmd_model_discovery_parses_models_endpoint_shape() -> None:
    models = parse_models_response(
        {
            "models": [
                {"model_id": "qwen3.6-flash", "display_name": "Qwen 3.6 Flash"},
                {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite"},
            ]
        }
    )

    assert [model.model_id for model in models] == ["qwen3.6-flash", "gemini-2.5-flash-lite"]


def test_okmd_candidate_selection_prefers_order_rejects_gemini_and_caps_three() -> None:
    catalog = [
        OKMDModel("llama-4-scout", "Llama 4 Scout"),
        OKMDModel("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite"),
        OKMDModel("qwen3.6-flash", "Qwen 3.6 Flash"),
        OKMDModel("deepseek-v4-flash", "DeepSeek V4 Flash"),
        OKMDModel("mistral-medium-3.1", "Mistral Medium 3.1"),
    ]

    selected = select_okmd_candidates(catalog, max_candidates=3)

    assert [model.model_id for model in selected] == [
        "deepseek-v4-flash",
        "qwen3.6-flash",
        "mistral-medium-3.1",
    ]
    assert all(model_family(model) != "Gemini" for model in selected)


def test_okmd_model_family_rejects_gemini_aliases() -> None:
    assert model_family(OKMDModel("gemini-2.5-flash-lite", "Gemini")) == "Gemini"
    assert model_family(OKMDModel("google/gemma-3", "Gemma")) == "Gemini"
    assert model_family(OKMDModel("deepseek-v4-flash", "DeepSeek")) == "DeepSeek"


def test_okmd_quota_estimate_uses_conservative_chars_plus_output_and_margin() -> None:
    estimate = estimate_pilot_tokens(["a" * 12, "b" * 24], output_tokens=256)

    assert estimate == 655


def test_okmd_quota_gate_requires_actual_remaining_tokens() -> None:
    quota = OKMDQuota(
        daily_quota_tokens=1000,
        daily_usage_tokens=100,
        daily_remaining_tokens=900,
    )
    assert validate_quota_gate(quota, estimated_tokens=700).status == "PASS"
    assert (
        validate_quota_gate(quota, estimated_tokens=901).status == "OKMD_QUOTA_INSUFFICIENT_FOR_120"
    )


def test_okmd_quota_gate_rejects_missing_quota() -> None:
    with pytest.raises(ValueError, match="daily_remaining_tokens"):
        validate_quota_gate(None, estimated_tokens=1)
