from __future__ import annotations

from pathlib import Path

import pytest

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from scripts import run_phase5a_local_pilot_v3 as v3


def _trace(example_id: str, label: str) -> JudgeEvaluationTrace:
    return JudgeEvaluationTrace.model_validate(
        {
            "example_id": example_id,
            "provider": v3.LOCAL_PROVIDER,
            "requested_model": v3.MODEL,
            "returned_model": v3.MODEL,
            "model_version": v3.EXPECTED_MODEL_DIGEST,
            "prediction": {
                "example_id": example_id,
                "label": label,
                "score": 0.9 if label == "HALLUCINATED" else 0.1,
                "support_score": 0.1 if label == "HALLUCINATED" else 0.9,
                "evaluator_name": "llm-judge",
                "evaluator_version": v3.CLASSIFICATION_SCHEMA_VERSION,
                "evaluator_config": {},
            },
            "decision": {"label": label, "confidence": 0.9},
            "api_success": True,
            "parse_success": True,
            "structured_output_status": "PASS",
            "requested_output_mode": "json-schema-strict",
            "actual_output_mode": "json-schema-strict",
            "provider_schema_enforced": True,
            "local_schema_validated": True,
            "finish_reason": "stop",
            "assistant_content_present": True,
            "assistant_content_length": 48,
            "usage": {"completion_tokens": 12, "prompt_tokens": 80},
            "reasoning_present": False,
        }
    )


def test_v3_is_a_new_classification_first_experiment() -> None:
    assert v3.PILOT_ID == "ragtruth-local-llm-judge-pilot-v3"
    assert v3.NUM_PREDICT == 128
    assert v3.DEFAULT_STATE.name == "phase5a-local-pilot-v3-state.json"
    assert len(v3.SYNTHETIC_PREFLIGHT_CASES) == 10
    assert v3._transport_config().num_ctx is None
    assert v3._transport_config().schema_hash == v3.schema_sha256(v3.CLASSIFICATION_OUTPUT_SCHEMA)


def test_v3_model_guard_rejects_digest_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        v3,
        "_ollama_metadata",
        lambda model: {
            "requested_model": model,
            "returned_model": model,
            "ollama_id": v3.EXPECTED_OLLAMA_ID,
            "weights_digest": "wrong",
            "model_digest": "wrong",
        },
    )

    with pytest.raises(RuntimeError, match="LOCAL_MODEL_DIGEST_MISMATCH"):
        v3._verify_model()


def test_v3_classification_validator_rejects_auxiliary_fields() -> None:
    assert v3._classification_validator_rule('{"label":"GROUNDED","confidence":0.8}') is None
    assert (
        v3._classification_validator_rule('{"label":"GROUNDED","confidence":0.8,"reason":"extra"}')
        == "EXTRA_PROPERTY:reason"
    )
    assert (
        v3._classification_validator_rule('{"label":"GROUNDED","confidence":2}')
        == "CONFIDENCE_RANGE"
    )


def test_v3_path_guard_does_not_overwrite_prior_experiments(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="MUST_NOT_OVERWRITE_PRIOR"):
        v3._assert_isolated_paths(v3.V2_STATE, tmp_path / "v3-report.json")


def test_v3_preflight_requires_all_ten_cases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = {
        "requested_model": v3.MODEL,
        "returned_model": v3.MODEL,
        "ollama_id": v3.EXPECTED_OLLAMA_ID,
        "weights_digest": v3.EXPECTED_WEIGHTS_DIGEST,
        "model_digest": v3.EXPECTED_MODEL_DIGEST,
        "ollama_version": "ollama version is 0.33.2",
        "quantization": "Q4_K_M",
        "parameter_size": "8.2B",
        "context_length": 40960,
    }
    monkeypatch.setattr(v3, "_verify_model", lambda: metadata)
    monkeypatch.setattr(v3, "_assert_clean_source_tree", lambda: None)
    monkeypatch.setattr(v3, "_git_head", lambda: "commit-v3")
    monkeypatch.setattr(v3, "_hardware_metadata", lambda: {"os": "test"})

    class FakeEvaluator:
        def evaluate_with_trace(
            self, context: str, response: str, example_id: str
        ) -> JudgeEvaluationTrace:
            label = (
                "HALLUCINATED"
                if "hallucinated" in example_id or "injection" in example_id
                else "GROUNDED"
            )
            return _trace(example_id, label)

    monkeypatch.setattr(v3, "_evaluator", lambda ignored: FakeEvaluator())
    artifact = tmp_path / "preflight.json"
    payload = v3._preflight(v3.argparse.Namespace(preflight_artifact=artifact))

    assert payload["LOCAL_PREFLIGHT"] == "PASS"
    assert payload["request_count"] == 10
    assert payload["api_success_count"] == 10
    assert payload["json_schema_success_count"] == 10
    assert payload["local_validation_success_count"] == 10
    assert payload["expected_label_match_count"] == 10
    assert payload["output_token_truncation_count"] == 0
