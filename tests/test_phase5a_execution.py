from __future__ import annotations

from pathlib import Path

import pytest

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction
from evalops.pilot.execution import (
    PilotRequestLimitError,
    PilotStateStore,
    RequestBudget,
    run_provider_pilot,
)
from evalops.pilot.models import PilotExampleMetadata, PilotManifest


def _manifest() -> PilotManifest:
    return PilotManifest(
        pilot_id="pilot",
        manifest_version="v1",
        dataset_revision="fixture",
        split="test",
        quality_filter=["good"],
        sampling_seed=1,
        sampling_strategy="fixture",
        records=[
            PilotExampleMetadata(
                example_id="a",
                source_id="s-a",
                task_type="QA",
                human_label=HallucinationLabel.GROUNDED,
                stratum="QA:GROUNDED",
            )
        ],
    )


def _trace(example_id: str, *, error_class: str | None = None) -> JudgeEvaluationTrace:
    return JudgeEvaluationTrace(
        example_id=example_id,
        provider="fake",
        requested_model="fake-model",
        prediction=(
            HallucinationPrediction(
                example_id=example_id,
                label=HallucinationLabel.GROUNDED,
            )
            if error_class is None
            else None
        ),
        api_success=error_class is None,
        parse_success=error_class is None,
        error_class=error_class,
    )


def test_successful_provider_example_is_skipped_on_resume(tmp_path: Path) -> None:
    calls = 0

    def evaluator(context: str, response: str, example_id: str) -> JudgeEvaluationTrace:
        nonlocal calls
        calls += 1
        return _trace(example_id)

    state = PilotStateStore(tmp_path / "state.json")
    examples = {"a": ("context", "response")}
    run_provider_pilot(_manifest(), examples, {"fake": evaluator}, state, RequestBudget(10))
    run_provider_pilot(_manifest(), examples, {"fake": evaluator}, state, RequestBudget(10))

    assert calls == 1


def test_transient_failures_retry_but_auth_and_quota_do_not(tmp_path: Path) -> None:
    transient_calls = 0

    def transient(context: str, response: str, example_id: str) -> JudgeEvaluationTrace:
        nonlocal transient_calls
        transient_calls += 1
        return _trace(example_id, error_class="API_RATE_LIMIT")

    state = PilotStateStore(tmp_path / "state.json")
    run_provider_pilot(
        _manifest(),
        {"a": ("context", "response")},
        {"fake": transient},
        state,
        RequestBudget(10),
        retry_sleep=lambda _: None,
    )
    assert transient_calls == 3

    for error_class in ("API_AUTH_ERROR", "API_QUOTA_ERROR"):
        calls = 0
        expected_error_class = error_class

        def permanent(
            context: str,
            response: str,
            example_id: str,
            expected_error: str = expected_error_class,
        ) -> JudgeEvaluationTrace:
            nonlocal calls
            calls += 1
            return _trace(example_id, error_class=expected_error)

        permanent_state = PilotStateStore(tmp_path / f"{error_class}.json")
        run_provider_pilot(
            _manifest(),
            {"a": ("context", "response")},
            {"fake": permanent},
            permanent_state,
            RequestBudget(10),
            retry_sleep=lambda _: None,
        )
        assert calls == 1


def test_request_budget_rejects_the_301st_request() -> None:
    budget = RequestBudget(300)
    for _ in range(300):
        budget.reserve()

    with pytest.raises(PilotRequestLimitError):
        budget.reserve()
