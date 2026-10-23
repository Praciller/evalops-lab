"""Fixed, versioned retrieval regression policy; shared comparator owns all decisions."""

from __future__ import annotations

from typing import Final, Literal

from evalops.regression.comparison import MetricDirection, MetricRule

WORKSPACE_RETRIEVAL_POLICY_VERSION: Final[Literal["workspace-retrieval-regression-v1"]] = (
    "workspace-retrieval-regression-v1"
)


def build_workspace_retrieval_rules(k: int) -> list[MetricRule]:
    """Five deterministic higher-is-better rules; zero allowed regression.

    No client-supplied rules, thresholds, or evaluator logic are accepted.
    """

    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("retrieval top_k must be a positive integer")
    names = (
        f"precision_at_{k}",
        f"recall_at_{k}",
        f"hit_rate_at_{k}",
        "mrr",
        f"ndcg_at_{k}",
    )
    return [
        MetricRule(
            metric_name=name,
            direction=MetricDirection.HIGHER_IS_BETTER,
            max_degradation=0.0,
        )
        for name in names
    ]
