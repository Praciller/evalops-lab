from __future__ import annotations

import pytest
from pydantic import ValidationError

from evalops.evaluators.judge.models import (
    JudgeClassificationDecision,
    JudgeDecision,
    JudgeLabel,
    parse_classification_judge_payload,
    parse_judge_payload,
)


def test_valid_hallucinated_decision_requires_unsupported_claim() -> None:
    decision = JudgeDecision(
        label=JudgeLabel.HALLUCINATED,
        confidence=0.9,
        unsupported_claims=["The answer invents a date."],
        reason="The date is absent from the supplied context.",
    )

    assert decision.label is JudgeLabel.HALLUCINATED


def test_valid_grounded_decision_requires_empty_unsupported_claims() -> None:
    decision = JudgeDecision(
        label=JudgeLabel.GROUNDED,
        confidence=0.8,
        unsupported_claims=[],
        reason="Every material claim is supported by the context.",
    )

    assert decision.label is JudgeLabel.GROUNDED


def test_label_and_claim_consistency_is_not_silently_repaired() -> None:
    with pytest.raises(ValidationError, match="unsupported_claims"):
        JudgeDecision(
            label=JudgeLabel.HALLUCINATED,
            confidence=0.9,
            unsupported_claims=[],
            reason="The answer is unsupported.",
        )

    with pytest.raises(ValidationError, match="unsupported_claims"):
        JudgeDecision(
            label=JudgeLabel.GROUNDED,
            confidence=0.9,
            unsupported_claims=["A claim"],
            reason="The answer is supported.",
        )


def test_confidence_and_reason_limits_are_enforced() -> None:
    with pytest.raises(ValidationError):
        JudgeDecision(
            label=JudgeLabel.GROUNDED,
            confidence=1.1,
            unsupported_claims=[],
            reason="Short.",
        )
    with pytest.raises(ValidationError):
        JudgeDecision(
            label=JudgeLabel.GROUNDED,
            confidence=0.5,
            unsupported_claims=[],
            reason="x" * 301,
        )


def test_parse_judge_payload_reports_schema_failure_without_repairing_it() -> None:
    parsed = parse_judge_payload(
        '{"label":"HALLUCINATED","confidence":0.9,"unsupported_claims":[],"reason":"bad"}'
    )

    assert parsed.success is False
    assert parsed.error_class == "SCHEMA_VALIDATION_ERROR"
    assert parsed.decision is None


def test_parse_judge_payload_accepts_valid_json() -> None:
    parsed = parse_judge_payload(
        '{"label":"GROUNDED","confidence":0.7,"unsupported_claims":[],"reason":"Supported."}'
    )

    assert parsed.success is True
    assert parsed.decision is not None
    assert parsed.decision.label is JudgeLabel.GROUNDED


def test_classification_contract_excludes_evidence_fields() -> None:
    decision = JudgeClassificationDecision(label=JudgeLabel.GROUNDED, confidence=0.7)

    assert decision.model_dump() == {"label": JudgeLabel.GROUNDED, "confidence": 0.7}
    with pytest.raises(ValidationError):
        JudgeClassificationDecision(
            label=JudgeLabel.GROUNDED,
            confidence=0.7,
            reason="must not be part of primary output",
        )


def test_parse_classification_payload_accepts_only_primary_fields() -> None:
    parsed = parse_classification_judge_payload('{"label":"HALLUCINATED","confidence":0.9}')
    rejected = parse_classification_judge_payload(
        '{"label":"HALLUCINATED","confidence":0.9,"reason":"extra"}'
    )

    assert parsed.success is True
    assert parsed.decision is not None
    assert parsed.decision.label is JudgeLabel.HALLUCINATED
    assert rejected.success is False
    assert rejected.error_class == "SCHEMA_VALIDATION_ERROR"
