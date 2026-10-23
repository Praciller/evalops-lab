"""Phase 6.3 Task 3: policy metadata and shared regression-authority parity."""

from __future__ import annotations

import pytest

from evalops.regression.comparison import (
    MetricDirection,
    RegressionStatus,
    compare_metrics,
)
from evalops.workspace.comparison.policy import (
    WORKSPACE_RETRIEVAL_POLICY_VERSION,
    build_workspace_retrieval_rules,
)


def test_policy_version_and_exact_five_zero_tolerance_rules() -> None:
    assert WORKSPACE_RETRIEVAL_POLICY_VERSION == "workspace-retrieval-regression-v1"
    rules = build_workspace_retrieval_rules(7)
    assert [rule.metric_name for rule in rules] == [
        "precision_at_7",
        "recall_at_7",
        "hit_rate_at_7",
        "mrr",
        "ndcg_at_7",
    ]
    assert all(rule.direction == MetricDirection.HIGHER_IS_BETTER for rule in rules)
    assert all(rule.max_degradation == 0.0 for rule in rules)
    assert all(rule.minimum_acceptable is None for rule in rules)
    assert all(rule.maximum_acceptable is None for rule in rules)


@pytest.mark.parametrize("k", [0, -1, 1.5, True, "10", None])
def test_invalid_top_k_rejected(k: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_workspace_retrieval_rules(k)  # type: ignore[arg-type]


def test_missing_metrics_fail_closed_using_shared_compare_metrics() -> None:
    base = {
        "precision_at_2": 0.5,
        "recall_at_2": 0.5,
        "hit_rate_at_2": 1.0,
        "mrr": 0.75,
        "ndcg_at_2": 0.8,
    }
    report = compare_metrics({"mrr": 0.75}, base, build_workspace_retrieval_rules(2))
    assert report.passed is False
    assert [item.status for item in report.comparisons] == [
        RegressionStatus.MISSING,
        RegressionStatus.MISSING,
        RegressionStatus.MISSING,
        RegressionStatus.PASS,
        RegressionStatus.MISSING,
    ]


def test_any_regression_is_reported_by_shared_comparator() -> None:
    base = {
        "precision_at_5": 0.50,
        "recall_at_5": 0.50,
        "hit_rate_at_5": 0.50,
        "mrr": 0.50,
        "ndcg_at_5": 0.50,
    }
    improved = {name: value + 0.10 for name, value in base.items()}
    passing = compare_metrics(improved, base, build_workspace_retrieval_rules(5))
    assert passing.passed is True
    assert all(item.status == RegressionStatus.PASS for item in passing.comparisons)

    degraded = dict(improved)
    degraded["recall_at_5"] = 0.499
    regressed = compare_metrics(degraded, base, build_workspace_retrieval_rules(5))
    assert regressed.passed is False
    assert [
        item.metric_name
        for item in regressed.comparisons
        if item.status == RegressionStatus.REGRESSION
    ] == ["recall_at_5"]


def test_equal_values_pass_and_finite_validation_stays_in_authoritative_comparator() -> None:
    baseline = {
        "precision_at_1": 1.0,
        "recall_at_1": 1.0,
        "hit_rate_at_1": 1.0,
        "mrr": 1.0,
        "ndcg_at_1": 1.0,
    }
    report = compare_metrics(baseline, baseline, build_workspace_retrieval_rules(1))
    assert report.passed is True
    assert all(c.delta == 0.0 for c in report.comparisons)

    with pytest.raises(ValueError, match="finite number"):
        compare_metrics(
            {**baseline, "mrr": float("nan")},
            baseline,
            build_workspace_retrieval_rules(1),
        )
