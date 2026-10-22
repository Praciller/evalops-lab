from __future__ import annotations

import pytest

from evalops.regression.comparison import (
    MetricDirection,
    MetricRule,
    RegressionStatus,
    compare_metrics,
)


def _rule(**overrides: object) -> MetricRule:
    values: dict[str, object] = {
        "metric_name": "recall_at_5",
        "direction": MetricDirection.HIGHER_IS_BETTER,
    }
    values.update(overrides)
    return MetricRule(**values)


def test_higher_is_better_metric_passes_without_regression() -> None:
    report = compare_metrics({"recall_at_5": 0.91}, {"recall_at_5": 0.90}, [_rule()])

    assert report.passed
    assert report.comparisons[0].status == RegressionStatus.PASS
    assert report.comparisons[0].delta == pytest.approx(0.01)


def test_exact_allowable_degradation_passes() -> None:
    report = compare_metrics(
        {"recall_at_5": 0.85},
        {"recall_at_5": 0.90},
        [_rule(max_degradation=0.05)],
    )

    assert report.passed


def test_degradation_beyond_allowance_is_a_regression() -> None:
    report = compare_metrics(
        {"recall_at_5": 0.849},
        {"recall_at_5": 0.90},
        [_rule(max_degradation=0.05)],
    )

    assert not report.passed
    assert report.comparisons[0].status == RegressionStatus.REGRESSION


def test_minimum_acceptable_threshold_is_independent_of_baseline() -> None:
    report = compare_metrics(
        {"recall_at_5": 0.69},
        {"recall_at_5": 0.80},
        [_rule(minimum_acceptable=0.70)],
    )

    assert not report.passed
    assert "minimum" in report.comparisons[0].reason


def test_lower_is_better_metric_uses_opposite_degradation_direction() -> None:
    rule = _rule(metric_name="hallucination_rate", direction=MetricDirection.LOWER_IS_BETTER)
    report = compare_metrics({"hallucination_rate": 0.12}, {"hallucination_rate": 0.10}, [rule])

    assert not report.passed
    assert report.comparisons[0].status == RegressionStatus.REGRESSION


def test_lower_is_better_metric_can_pass_at_exact_allowance() -> None:
    rule = _rule(
        metric_name="hallucination_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        max_degradation=0.02,
    )
    report = compare_metrics({"hallucination_rate": 0.12}, {"hallucination_rate": 0.10}, [rule])

    assert report.passed


def test_missing_metric_is_explicit_and_fails_the_report() -> None:
    report = compare_metrics({}, {"recall_at_5": 0.90}, [_rule()])

    assert not report.passed
    assert report.comparisons[0].status == RegressionStatus.MISSING


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True])
@pytest.mark.parametrize("side", ["current", "baseline"])
def test_invalid_metric_values_never_pass_regression(invalid: float | bool, side: str) -> None:
    current: dict[str, float] = {"recall_at_5": 0.91}
    baseline: dict[str, float] = {"recall_at_5": 0.90}
    if side == "current":
        current["recall_at_5"] = invalid
    else:
        baseline["recall_at_5"] = invalid

    with pytest.raises(ValueError, match="must be a finite number"):
        compare_metrics(current, baseline, [_rule()])


@pytest.mark.parametrize("name", ["minimum_acceptable", "maximum_acceptable", "max_degradation"])
def test_policy_rejects_non_finite_thresholds(name: str) -> None:
    with pytest.raises(ValueError):
        _rule(**{name: float("nan")})


def test_empty_regression_policy_is_not_a_passing_report() -> None:
    with pytest.raises(ValueError, match="at least one metric rule"):
        compare_metrics({"recall_at_5": 0.9}, {"recall_at_5": 0.8}, [])
