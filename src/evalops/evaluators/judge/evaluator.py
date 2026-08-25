"""Provider-independent strict-groundedness evaluator."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from evalops.evaluators.judge.models import (
    JudgeDecision,
    JudgeParseResult,
    parse_judge_payload,
)
from evalops.evaluators.judge.prompt import (
    JUDGE_OUTPUT_SCHEMA,
    JUDGE_PROMPT_SHA256,
    JUDGE_PROMPT_VERSION,
    JUDGE_SCHEMA_VERSION,
    render_judge_prompt,
)
from evalops.evaluators.judge.providers import JudgeProvider, SamplingConfig
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction


class JudgeEvaluationTrace(BaseModel):
    """Safe per-call trace; raw final content is deliberately excluded."""

    model_config = ConfigDict(extra="forbid")

    example_id: str
    provider: str
    requested_model: str
    returned_model: str | None = None
    prediction: HallucinationPrediction | None = None
    decision: JudgeDecision | None = None
    api_success: bool = False
    parse_success: bool = False
    structured_output_status: str = "NOT_RUN"
    requested_output_mode: str = "json-schema-strict"
    actual_output_mode: str = "json-schema-strict"
    provider_schema_enforced: bool = False
    local_schema_validated: bool = True
    http_status: int | None = None
    response_object_type: str | None = None
    finish_reason: str | None = None
    assistant_content_present: bool = False
    assistant_content_length: int = 0
    reasoning_present: bool = False
    reasoning_length: int = 0
    tool_calls_present: bool = False
    usage_metadata_present: bool = False
    usage: dict[str, int | float | str] | None = None
    request_id: str | None = None
    latency_ms: float | None = None
    error_class: str | None = None
    safe_error_summary: str | None = None


class JudgeEvaluationError(RuntimeError):
    """Raised by the protocol-compatible evaluate method for failed calls."""


def _prediction_from_decision(
    decision: JudgeDecision,
    *,
    example_id: str,
    evaluator_config: dict[str, Any],
) -> HallucinationPrediction:
    label = HallucinationLabel(decision.label.value)
    score = (
        decision.confidence
        if label is HallucinationLabel.HALLUCINATED
        else round(1.0 - decision.confidence, 12)
    )
    return HallucinationPrediction(
        example_id=example_id,
        label=label,
        score=score,
        support_score=1.0 - score,
        evaluator_name="llm-judge",
        evaluator_version=JUDGE_PROMPT_VERSION,
        evaluator_config=evaluator_config,
    )


class LLMJudgeEvaluator:
    """Adapt any structured judge provider to the existing hallucination contract."""

    name = "llm-judge"
    version = JUDGE_PROMPT_VERSION

    def __init__(
        self,
        provider: JudgeProvider,
        *,
        sampling: SamplingConfig | None = None,
    ) -> None:
        self.provider = provider
        self.sampling = sampling or SamplingConfig()

    @property
    def config(self) -> dict[str, Any]:
        return {
            "provider": self.provider.provider_name,
            "base_url_identifier": self.provider.base_url_identifier,
            "model": self.provider.model,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "prompt_sha256": JUDGE_PROMPT_SHA256,
            "schema_version": JUDGE_SCHEMA_VERSION,
            "output_mode": self.provider.output_mode,
            "sampling": {
                "temperature": self.sampling.temperature,
                "top_p": self.sampling.top_p,
                "max_output_tokens": self.sampling.max_output_tokens,
                "reasoning_effort": self.sampling.reasoning_effort,
                "include_reasoning": self.sampling.include_reasoning,
            },
        }

    def evaluate_with_trace(
        self,
        context: str,
        response: str,
        example_id: str = "",
    ) -> JudgeEvaluationTrace:
        prompt = render_judge_prompt(context, response)
        call = self.provider.judge(
            prompt,
            schema=JUDGE_OUTPUT_SCHEMA,
            config=self.sampling,
        )
        parse_result: JudgeParseResult | None = None
        if call.api_success and call.assistant_content:
            parse_result = parse_judge_payload(call.assistant_content)
        prediction: HallucinationPrediction | None = None
        decision: JudgeDecision | None = None
        error_class = call.error_class
        safe_error_summary = call.safe_error_summary
        structured_status = (
            "STRUCTURED_OUTPUT_RUNTIME_FAILED" if not call.api_success else "PARSE_FAILED"
        )
        if parse_result is not None:
            structured_status = "PASS" if parse_result.success else "PARSE_FAILED"
            decision = parse_result.decision
            if decision is not None:
                prediction = _prediction_from_decision(
                    decision,
                    example_id=example_id,
                    evaluator_config=self.config,
                )
            else:
                error_class = parse_result.error_class
                safe_error_summary = parse_result.safe_error_summary
        return JudgeEvaluationTrace(
            example_id=example_id,
            provider=call.provider,
            requested_model=call.requested_model,
            returned_model=call.returned_model,
            prediction=prediction,
            decision=decision,
            api_success=call.api_success,
            parse_success=prediction is not None,
            structured_output_status=structured_status,
            requested_output_mode=call.requested_output_mode,
            actual_output_mode=call.actual_output_mode,
            provider_schema_enforced=call.provider_schema_enforced,
            local_schema_validated=call.local_schema_validated,
            http_status=call.http_status,
            response_object_type=call.response_object_type,
            finish_reason=call.finish_reason,
            assistant_content_present=call.assistant_content_present,
            assistant_content_length=call.assistant_content_length,
            reasoning_present=call.reasoning_present,
            reasoning_length=call.reasoning_length,
            tool_calls_present=call.tool_calls_present,
            usage_metadata_present=call.usage_metadata_present,
            usage=call.usage,
            request_id=call.request_id,
            latency_ms=call.latency_ms,
            error_class=error_class,
            safe_error_summary=safe_error_summary,
        )

    def evaluate(
        self,
        context: str,
        response: str,
        *,
        example_id: str = "",
    ) -> HallucinationPrediction:
        trace = self.evaluate_with_trace(context, response, example_id)
        if trace.prediction is None:
            raise JudgeEvaluationError(trace.safe_error_summary or "LLM judge evaluation failed")
        return trace.prediction
