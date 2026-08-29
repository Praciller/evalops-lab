from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from scripts import run_phase5a_local_pilot_v2 as v2


def _trace(**overrides: object) -> JudgeEvaluationTrace:
    values: dict[str, object] = {
        "example_id": "example-1",
        "provider": v2.LOCAL_PROVIDER,
        "requested_model": v2.MODEL,
        "model_version": v2.EXPECTED_MODEL_DIGEST,
        "api_success": True,
        "finish_reason": "stop",
        "assistant_content_present": True,
        "assistant_content_length": 120,
        "usage": {"completion_tokens": 20, "prompt_tokens": 80},
        "reasoning_present": False,
        "reasoning_length": 0,
        "error_class": "SCHEMA_VALIDATION_ERROR",
    }
    values.update(overrides)
    return JudgeEvaluationTrace.model_validate(values)


def test_v2_is_a_separate_experiment_and_preserves_exact_manifest_contract() -> None:
    assert v2.PILOT_ID == "ragtruth-local-llm-judge-pilot-v2"
    assert v2.FROZEN_MANIFEST_ID == "ragtruth-llm-judge-pilot-v1"
    assert v2.FROZEN_SEED == 20260825
    assert v2.DEFAULT_STATE.name == "phase5a-local-pilot-v2-state.json"
    assert v2.DEFAULT_STATE != v2.V1_STATE
    assert len(v2.SYNTHETIC_PREFLIGHT_CASES) == 6
    assert [case[3] for case in v2.SYNTHETIC_PREFLIGHT_CASES] == [
        "GROUNDED",
        "GROUNDED",
        "HALLUCINATED",
        "HALLUCINATED",
        "HALLUCINATED",
        "GROUNDED",
    ]


def test_v2_model_guard_rejects_any_digest_or_model_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v2,
        "_ollama_metadata",
        lambda model: {
            "requested_model": model,
            "returned_model": model,
            "ollama_id": v2.EXPECTED_OLLAMA_ID,
            "weights_digest": "wrong",
            "model_digest": "wrong",
        },
    )

    with pytest.raises(RuntimeError, match="LOCAL_MODEL_DIGEST_MISMATCH"):
        v2._verify_model()


def test_v2_failure_diagnostic_preserves_safe_metadata_and_failed_raw_output() -> None:
    content = '{"label":"WRONG","confidence":1.4,"unsupported_claims":[]}'
    diagnostic = v2._diagnostic_attempt(
        _trace(assistant_content_length=len(content)),
        content,
        attempt=1,
    )

    assert diagnostic["json_parse_status"] == "PASS"
    assert diagnostic["schema_validation_status"] == "FAIL"
    assert "INVALID_ENUM" in str(diagnostic["validator_rule"])
    assert diagnostic["eval_count"] == 20
    assert diagnostic["prompt_eval_count"] == 80
    assert diagnostic["thinking_present"] is False
    assert diagnostic["content_sha256"] is not None
    assert diagnostic["raw_model_output"] == content
    assert "source" not in json.dumps(diagnostic).casefold()


def test_v2_diagnostic_classifies_empty_and_truncated_outputs() -> None:
    empty = v2._diagnostic_attempt(
        _trace(
            assistant_content_present=False,
            assistant_content_length=0,
            finish_reason="stop",
            error_class="PARSE_ERROR",
        ),
        None,
        attempt=1,
    )
    truncated = v2._diagnostic_attempt(
        _trace(
            finish_reason="length",
            error_class="PARSE_ERROR",
            assistant_content_length=256,
        ),
        "{" * 256,
        attempt=1,
    )

    assert empty["json_parse_status"] == "EMPTY_CONTENT"
    assert empty["raw_model_output"] is None
    assert truncated["finish_reason"] == "length"
    assert truncated["eval_count"] == 20


def test_v2_diagnostics_are_atomically_isolated_from_v1(tmp_path: Path) -> None:
    path = tmp_path / "v2-diagnostics.json"
    store = v2._FailureDiagnostics(path)
    trace = _trace(example_id="safe-id")
    store.append(trace, "not json", attempt=1)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["experiment_id"] == v2.PILOT_ID
    assert payload["raw_reasoning_persisted"] is False
    assert payload["attempts"][0]["example_id"] == "safe-id"
    assert "phase5a-local-pilot-v1" not in json.dumps(payload)


def test_v2_path_guard_rejects_v1_state_or_report() -> None:
    with pytest.raises(RuntimeError, match="MUST_NOT_OVERWRITE_V1"):
        v2._assert_v2_paths(v2.V1_STATE, v2.DEFAULT_REPORT)
    with pytest.raises(RuntimeError, match="MUST_NOT_OVERWRITE_V1"):
        v2._assert_v2_paths(v2.DEFAULT_STATE, v2.V1_REPORT)


def test_v2_transport_config_preserves_absent_v1_context_and_keep_alive() -> None:
    config = v2._transport_config()
    assert config.model == v2.MODEL
    assert config.model_digest == v2.EXPECTED_MODEL_DIGEST
    assert config.num_predict == 512
    assert config.num_ctx is None
    assert config.keep_alive is None
    assert config.think is False
    assert config.schema_hash == v2.schema_sha256(v2.JUDGE_OUTPUT_SCHEMA)


def test_v2_preflight_artifact_is_safe_when_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = {
        "requested_model": v2.MODEL,
        "returned_model": v2.MODEL,
        "ollama_id": v2.EXPECTED_OLLAMA_ID,
        "weights_digest": v2.EXPECTED_WEIGHTS_DIGEST,
        "model_digest": v2.EXPECTED_MODEL_DIGEST,
        "ollama_version": "ollama version is 0.33.2",
        "quantization": "Q4_K_M",
        "parameter_size": "8.2B",
        "context_length": 40960,
    }
    monkeypatch.setattr(v2, "_verify_model", lambda: metadata)
    monkeypatch.setattr(v2, "_assert_clean_source_tree", lambda: None)
    monkeypatch.setattr(v2, "_git_head", lambda: "commit-v2")
    monkeypatch.setattr(v2, "_hardware_metadata", lambda: {"os": "test"})

    class FakeEvaluator:
        def evaluate_with_trace(
            self, context: str, response: str, example_id: str
        ) -> JudgeEvaluationTrace:
            label = (
                "HALLUCINATED"
                if "hallucinated" in example_id or "injection" in example_id
                else "GROUNDED"
            )
            decision = {
                "label": label,
                "confidence": 0.9,
                "unsupported_claims": ["unsupported"] if label == "HALLUCINATED" else [],
                "reason": "test",
            }
            return JudgeEvaluationTrace.model_validate(
                {
                    "example_id": example_id,
                    "provider": v2.LOCAL_PROVIDER,
                    "requested_model": v2.MODEL,
                    "returned_model": v2.MODEL,
                    "model_version": v2.EXPECTED_MODEL_DIGEST,
                    "api_success": True,
                    "parse_success": True,
                    "structured_output_status": "PASS",
                    "requested_output_mode": "json-schema-strict",
                    "actual_output_mode": "json-schema-strict",
                    "provider_schema_enforced": True,
                    "local_schema_validated": True,
                    "finish_reason": "stop",
                    "assistant_content_present": True,
                    "assistant_content_length": 20,
                    "decision": decision,
                    "prediction": {
                        "example_id": example_id,
                        "label": label,
                        "score": 0.9 if label == "HALLUCINATED" else 0.1,
                        "support_score": 0.1 if label == "HALLUCINATED" else 0.9,
                        "evaluator_name": "llm-judge",
                        "evaluator_version": v2.JUDGE_PROMPT_VERSION,
                        "evaluator_config": {},
                    },
                }
            )

    monkeypatch.setattr(v2, "LLMJudgeEvaluator", lambda provider, sampling: FakeEvaluator())
    artifact = tmp_path / "preflight.json"
    payload = v2._preflight(v2.argparse.Namespace(preflight_artifact=artifact))

    assert payload["LOCAL_PREFLIGHT"] == "PASS"
    assert payload["api_success_count"] == 6
    assert payload["json_schema_success_count"] == 6
    assert payload["local_validation_success_count"] == 6
    assert payload["thinking_output_count"] == 0
    assert payload["raw_model_response_persisted"] is False
