from __future__ import annotations

from typing import Any

from evalops.evaluators.judge.evaluator import LLMJudgeEvaluator
from evalops.evaluators.judge.models import JudgeLabel
from evalops.evaluators.judge.providers import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
    ProviderHTTPResponse,
)


class FixedTransport:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> ProviderHTTPResponse:
        return ProviderHTTPResponse(status_code=self.status_code, body=self.body)


def test_gemini_response_maps_to_grounded_prediction() -> None:
    adapter = GeminiProviderAdapter(
        "secret-not-persisted",
        transport=FixedTransport(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"label":"GROUNDED","confidence":0.8,'
                                        '"unsupported_claims":[],"reason":"Supported."}'
                                    )
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "modelVersion": "gemini-2.5-flash-lite",
            }
        ),
    )
    evaluator = LLMJudgeEvaluator(adapter)

    trace = evaluator.evaluate_with_trace("The source says seven.", "The answer says seven.", "r1")

    assert trace.prediction is not None
    assert trace.prediction.label.value == "GROUNDED"
    assert trace.prediction.score == 0.2
    assert trace.structured_output_status == "PASS"
    assert trace.parse_success is True


def test_groq_response_maps_to_hallucinated_prediction_and_ignores_reasoning() -> None:
    adapter = GroqProviderAdapter(
        "secret-not-persisted",
        transport=FixedTransport(
            {
                "object": "chat.completion",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"label":"HALLUCINATED","confidence":0.9,'
                                '"unsupported_claims":["The answer invents a date."],'
                                '"reason":"The date is absent."}'
                            ),
                            "reasoning": "hidden reasoning must not persist",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
            }
        ),
    )
    evaluator = LLMJudgeEvaluator(adapter)

    trace = evaluator.evaluate_with_trace(
        "The source says seven.", "The answer invents a date.", "r2"
    )

    assert trace.prediction is not None
    assert trace.prediction.label.value == "HALLUCINATED"
    assert trace.prediction.score == 0.9
    assert trace.reasoning_present is True
    assert "hidden reasoning" not in trace.model_dump_json()


def test_api_error_is_a_controlled_failed_trace() -> None:
    adapter = GeminiProviderAdapter(
        "secret-not-persisted",
        transport=FixedTransport({"error": "private"}, status_code=401),
    )
    evaluator = LLMJudgeEvaluator(adapter)

    trace = evaluator.evaluate_with_trace("context", "response", "r3")

    assert trace.prediction is None
    assert trace.api_success is False
    assert trace.error_class == "API_AUTH_ERROR"
    assert "private" not in trace.model_dump_json()


def test_public_evaluator_output_is_separate_from_judge_reason() -> None:
    adapter = GroqProviderAdapter(
        "secret-not-persisted",
        transport=FixedTransport(
            {
                "object": "chat.completion",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"label":"GROUNDED","confidence":0.6,'
                                '"unsupported_claims":[],"reason":"Supported."}'
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ),
    )
    prediction = LLMJudgeEvaluator(adapter).evaluate("context", "response", example_id="r4")

    assert prediction.label is not JudgeLabel.HALLUCINATED
    assert '"reason":"Supported."' not in prediction.model_dump_json()
