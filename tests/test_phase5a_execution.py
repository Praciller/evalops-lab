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
from evalops.pilot.models import PilotExampleMetadata, PilotManifest, PilotRunRecord
from evalops.pilot.rate_limit import (
    DailyQuotaExhaustedError,
    RateAwareRequestScheduler,
    RateLimitCircuitBreakerError,
)


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


def _trace(
    example_id: str,
    *,
    error_class: str | None = None,
    provider: str = "fake",
    api_success: bool | None = None,
) -> JudgeEvaluationTrace:
    return JudgeEvaluationTrace(
        example_id=example_id,
        provider=provider,
        requested_model="fake-model",
        prediction=(
            HallucinationPrediction(
                example_id=example_id,
                label=HallucinationLabel.GROUNDED,
            )
            if error_class is None
            else None
        ),
        api_success=error_class is None if api_success is None else api_success,
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


def test_successful_state_record_is_immutable(tmp_path: Path) -> None:
    state = PilotStateStore(tmp_path / "state.json")
    first = _trace("a")
    state.upsert(
        PilotRunRecord(
            provider="fake",
            example_id="a",
            attempt=1,
            status="SUCCESS",
            trace=first,
        )
    )
    replacement = _trace("a")
    replacement = replacement.model_copy(update={"requested_model": "different"})

    with pytest.raises(ValueError, match="immutable"):
        state.upsert(
            PilotRunRecord(
                provider="fake",
                example_id="a",
                attempt=2,
                status="SUCCESS",
                trace=replacement,
            )
        )


def test_unlimited_request_budget_has_no_artificial_ceiling() -> None:
    budget = RequestBudget(None)
    for _ in range(301):
        budget.reserve()

    assert budget.requests_used == 301


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


def test_okmd_parse_failure_regenerates_once_with_same_evaluator(tmp_path: Path) -> None:
    calls = 0

    def evaluator(context: str, response: str, example_id: str) -> JudgeEvaluationTrace:
        nonlocal calls
        calls += 1
        return _trace(
            example_id,
            provider="okmd",
            error_class="PARSE_ERROR" if calls == 1 else None,
            api_success=True,
        )

    state = PilotStateStore(tmp_path / "state.json")
    records = run_provider_pilot(
        _manifest(),
        {"a": ("context", "response")},
        {"okmd": evaluator},
        state,
        RequestBudget(10),
        parse_regenerations={"okmd": 1},
    )

    assert calls == 2
    assert records[0].status == "SUCCESS"
    assert records[0].attempt == 2


def test_rate_aware_scheduler_paces_requests_and_honors_retry_delay() -> None:
    current_time = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return current_time

    def sleep(seconds: float) -> None:
        nonlocal current_time
        sleeps.append(seconds)
        current_time += seconds

    scheduler = RateAwareRequestScheduler(
        min_interval_seconds=10.0,
        clock=clock,
        sleep=sleep,
    )
    scheduler.before_request()
    scheduler.observe("API_SUCCESS")
    scheduler.before_request()
    scheduler.observe("API_RATE_LIMIT", retry_after_seconds=17.0)
    scheduler.wait_before_retry()

    assert sleeps == [10.0, 17.0]
    assert scheduler.rate_limit_count == 1


def test_rate_aware_scheduler_stops_after_three_consecutive_rate_limits() -> None:
    scheduler = RateAwareRequestScheduler(min_interval_seconds=0.0, sleep=lambda _: None)

    scheduler.observe("API_RATE_LIMIT")
    scheduler.observe("API_RATE_LIMIT")
    with pytest.raises(RateLimitCircuitBreakerError, match="RATE_LIMIT_STILL_BLOCKING"):
        scheduler.observe("API_RATE_LIMIT")


def test_rate_aware_scheduler_stops_immediately_on_daily_quota_metadata() -> None:
    scheduler = RateAwareRequestScheduler(min_interval_seconds=0.0, sleep=lambda _: None)

    with pytest.raises(DailyQuotaExhaustedError, match="DAILY_QUOTA_EXHAUSTED"):
        scheduler.observe("API_RATE_LIMIT", rate_limit_dimension="RPD")


def test_pilot_execution_uses_scheduler_and_preserves_failed_id_for_resume(tmp_path: Path) -> None:
    calls = 0

    def evaluator(context: str, response: str, example_id: str) -> JudgeEvaluationTrace:
        nonlocal calls
        calls += 1
        return _trace(example_id, error_class="API_RATE_LIMIT")

    state = PilotStateStore(tmp_path / "state.json")
    scheduler = RateAwareRequestScheduler(min_interval_seconds=0.0, sleep=lambda _: None)
    with pytest.raises(RateLimitCircuitBreakerError):
        run_provider_pilot(
            _manifest(),
            {"a": ("context", "response")},
            {"fake": evaluator},
            state,
            RequestBudget(10),
            max_retries=2,
            scheduler=scheduler,
        )

    assert calls == 3
    assert state.get("fake", "a") is not None
    assert state.get("fake", "a").status == "FAILED"
