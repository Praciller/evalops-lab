"""Threshold-aware comparison of evaluation metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, Field


class MetricDirection(StrEnum):
    """Whether larger or smaller metric values are preferred."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class RegressionStatus(StrEnum):
    """Outcome for one configured metric."""

    PASS = "PASS"
    REGRESSION = "REGRESSION"
    MISSING = "MISSING"


class MetricRule(BaseModel):
    """Policy for an individual metric."""

    metric_name: str = Field(min_length=1)
    direction: MetricDirection
    minimum_acceptable: float | None = None
    maximum_acceptable: float | None = None
    max_degradation: float = Field(default=0.0, ge=0.0)


class MetricComparison(BaseModel):
    """Traceable comparison between baseline and current values."""

    metric_name: str
    direction: MetricDirection
    baseline: float | None
    current: float | None
    delta: float | None
    status: RegressionStatus
    reason: str


class RegressionReport(BaseModel):
    """Aggregate regression result."""

    passed: bool
    comparisons: list[MetricComparison]


def _compare_one(
    current_metrics: Mapping[str, float],
    baseline_metrics: Mapping[str, float],
    rule: MetricRule,
) -> MetricComparison:
    current = current_metrics.get(rule.metric_name)
    baseline = baseline_metrics.get(rule.metric_name)
    if current is None:
        return MetricComparison(
            metric_name=rule.metric_name,
            direction=rule.direction,
            baseline=baseline,
            current=None,
            delta=None,
            status=RegressionStatus.MISSING,
            reason="current result does not contain this metric",
        )
    if rule.direction == MetricDirection.HIGHER_IS_BETTER and rule.minimum_acceptable is not None:
        if current < rule.minimum_acceptable:
            return MetricComparison(
                metric_name=rule.metric_name,
                direction=rule.direction,
                baseline=baseline,
                current=current,
                delta=current - baseline if baseline is not None else None,
                status=RegressionStatus.REGRESSION,
                reason=f"below minimum acceptable value {rule.minimum_acceptable}",
            )
    if rule.direction == MetricDirection.LOWER_IS_BETTER and rule.maximum_acceptable is not None:
        if current > rule.maximum_acceptable:
            return MetricComparison(
                metric_name=rule.metric_name,
                direction=rule.direction,
                baseline=baseline,
                current=current,
                delta=current - baseline if baseline is not None else None,
                status=RegressionStatus.REGRESSION,
                reason=f"above maximum acceptable value {rule.maximum_acceptable}",
            )
    if baseline is None:
        return MetricComparison(
            metric_name=rule.metric_name,
            direction=rule.direction,
            baseline=None,
            current=current,
            delta=None,
            status=RegressionStatus.MISSING,
            reason="baseline result does not contain this metric",
        )

    delta = current - baseline
    if rule.direction == MetricDirection.HIGHER_IS_BETTER:
        regressed = current < baseline - rule.max_degradation
    else:
        regressed = current > baseline + rule.max_degradation
    return MetricComparison(
        metric_name=rule.metric_name,
        direction=rule.direction,
        baseline=baseline,
        current=current,
        delta=delta,
        status=RegressionStatus.REGRESSION if regressed else RegressionStatus.PASS,
        reason=(
            f"degradation exceeded allowance of {rule.max_degradation}"
            if regressed
            else "within configured regression allowance"
        ),
    )


def compare_metrics(
    current_metrics: Mapping[str, float],
    baseline_metrics: Mapping[str, float],
    rules: Sequence[MetricRule],
) -> RegressionReport:
    """Compare configured metrics and fail closed on missing evidence."""

    comparisons = [_compare_one(current_metrics, baseline_metrics, rule) for rule in rules]
    return RegressionReport(
        passed=all(comparison.status == RegressionStatus.PASS for comparison in comparisons),
        comparisons=comparisons,
    )
