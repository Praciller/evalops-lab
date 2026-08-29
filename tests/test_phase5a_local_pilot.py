from __future__ import annotations

import pytest

from scripts.run_phase5a_local_pilot import (
    FALLBACK_MODEL,
    GEMINI_STATE,
    PILOT_ID,
    PREFERRED_MODEL,
    _assert_no_prompt_leakage,
    _fallback_eligible,
    _local_recommendation,
    _ollama_metadata,
)


def test_local_experiment_has_separate_identity_and_state_from_gemini() -> None:
    assert PILOT_ID == "ragtruth-local-llm-judge-pilot-v1"
    assert PREFERRED_MODEL == "qwen3:8b"
    assert FALLBACK_MODEL == "qwen3:4b"
    assert GEMINI_STATE.name == "phase5a-pilot-state.json"


def test_local_prompt_leakage_guard_accepts_only_context_response_pairs() -> None:
    _assert_no_prompt_leakage({"id": ("context", "response")})

    with pytest.raises(ValueError, match="LEAKAGE"):
        _assert_no_prompt_leakage({"id": {"context": "context", "label": "GROUNDED"}})


def test_fallback_is_only_eligible_for_resource_or_load_failures() -> None:
    assert _fallback_eligible({"errors": ["LOCAL_OOM"]}) is True
    assert _fallback_eligible({"errors": ["LOCAL_RESOURCE_ERROR"]}) is True
    assert _fallback_eligible({"errors": ["LOCAL_MODEL_NOT_FOUND"]}) is True
    assert _fallback_eligible({"errors": ["SCHEMA_VALIDATION_ERROR"]}) is False
    assert _fallback_eligible({"errors": ["LOCAL_TIMEOUT"]}) is False


def test_ollama_metadata_uses_safe_model_and_weights_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.run_phase5a_local_pilot as local_pilot

    monkeypatch.setattr(
        local_pilot,
        "_ollama_show",
        lambda model: {
            "model": model,
            "details": {
                "format": "gguf",
                "parameter_size": "8.2B",
                "quantization_level": "Q4_K_M",
            },
            "model_info": {"qwen3.context_length": 40960},
            "capabilities": ["completion", "thinking"],
        },
    )
    outputs = {
        ("ollama", "--version"): "ollama version is 0.33.2",
        ("ollama", "list"): "NAME ID SIZE MODIFIED\nqwen3:8b 500a1f067a9f 5.2 GB now",
        (
            "ollama",
            "show",
            "qwen3:8b",
            "--modelfile",
        ): "FROM sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f",
    }

    monkeypatch.setattr(
        local_pilot,
        "_run_command",
        lambda args, timeout=30.0: outputs[tuple(args)],
    )

    metadata = _ollama_metadata("qwen3:8b")

    assert metadata["model_digest"] == (
        "ollama-id:500a1f067a9f;"
        "weights:sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f"
    )
    assert metadata["quantization"] == "Q4_K_M"
    assert metadata["context_length"] == 40960
    assert metadata["thinking_mode"] == "OFF"


def test_local_recommendation_compares_against_hhem_without_authorizing_run() -> None:
    local = {
        "missing_count": 0,
        "parse_success_rate": 1.0,
        "metrics": {
            "balanced_accuracy": 0.9,
            "f1": 0.9,
            "false_positive_rate": 0.1,
        },
    }
    hhem = {
        "metrics": {
            "balanced_accuracy": 0.8,
            "f1": 0.8,
            "false_positive_rate": 0.2,
        }
    }
    comparison = {
        "categories": {
            "CANDIDATE_ONLY_CORRECT": ["local"],
            "BASELINE_ONLY_CORRECT": [],
        }
    }

    recommendation = _local_recommendation(local, hhem, comparison)

    assert recommendation["status"] == "RECOMMEND_FULL_LOCAL_RUN"
    assert recommendation["decision_gate"] == "OWNER_AUTHORIZATION_REQUIRED"
    assert recommendation["full_2675_run_started"] is False
