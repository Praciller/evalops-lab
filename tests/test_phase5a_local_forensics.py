from __future__ import annotations

from scripts.run_phase5a_local_forensics import (
    _failure_breakdown,
    classify_assistant_content,
)


def test_forensics_classifies_empty_and_invalid_json_without_repair() -> None:
    assert classify_assistant_content(None)["category"] == "EMPTY_CONTENT"
    assert classify_assistant_content("```json\n{}\n```")["category"] == "JSON_CODE_FENCE"
    assert classify_assistant_content('{"label":')["category"] == "TRUNCATED_JSON"


def test_forensics_classifies_structural_schema_failures() -> None:
    missing = '{"label":"GROUNDED"}'
    invalid_label = '{"label":"MAYBE","confidence":0.5,"unsupported_claims":[],"reason":"ok"}'
    out_of_range = '{"label":"GROUNDED","confidence":2,"unsupported_claims":[],"reason":"ok"}'

    assert classify_assistant_content(missing)["category"] == "SCHEMA_MISSING_FIELD"
    assert classify_assistant_content(invalid_label)["category"] == "INVALID_LABEL_ENUM"
    assert classify_assistant_content(out_of_range)["category"] == "CONFIDENCE_OUT_OF_RANGE"


def test_forensics_classifies_semantic_consistency_without_changing_values() -> None:
    payload = (
        '{"label":"GROUNDED","confidence":0.5,"unsupported_claims":["claim"],'
        '"reason":"the claim is unsupported"}'
    )

    result = classify_assistant_content(payload)

    assert result["category"] == "LABEL_CLAIM_CONSISTENCY_FAILURE"
    assert result["json_parse_success"] is True


def test_forensics_uses_finish_reason_to_identify_output_token_limit() -> None:
    state = {
        "records": {
            "local-ollama:one": {
                "example_id": "one",
                "status": "FAILED",
                "trace": {"error_class": "PARSE_ERROR", "finish_reason": "length"},
            },
            "local-ollama:two": {
                "example_id": "two",
                "status": "FAILED",
                "trace": {"error_class": "SCHEMA_VALIDATION_ERROR", "finish_reason": "stop"},
            },
        }
    }

    result = _failure_breakdown(state, ["one", "two"])

    assert result["OUTPUT_TOKEN_LIMIT"]["example_ids"] == ["one"]
    assert result["PERSISTED_SCHEMA_VALIDATION_SUBTYPE_UNKNOWN"]["example_ids"] == ["two"]
