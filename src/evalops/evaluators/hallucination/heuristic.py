"""Small deterministic overlap baseline; not a factuality judge."""

from __future__ import annotations

import re

from evalops.models.hallucination import HallucinationLabel, HallucinationPrediction

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\W_]+", flags=re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text)}


class HeuristicHallucinationEvaluator:
    """Classify as hallucinated when response token support is below a fixed threshold."""

    name = "heuristic-baseline"
    version = "heuristic-baseline-v1"

    def __init__(self, overlap_threshold: float = 0.4) -> None:
        if not 0.0 <= overlap_threshold <= 1.0:
            raise ValueError("overlap_threshold must be between 0 and 1")
        self.overlap_threshold = overlap_threshold

    @property
    def config(self) -> dict[str, float | str]:
        return {
            "overlap_threshold": self.overlap_threshold,
            "threshold_selection": "fixed-v1-not-tuned-on-test",
        }

    def evaluate(
        self, context: str, response: str, *, example_id: str = ""
    ) -> HallucinationPrediction:
        response_tokens = _tokens(response)
        context_tokens = _tokens(context)
        if not response_tokens:
            support = 1.0
        elif not context_tokens:
            support = 0.0
        else:
            support = len(response_tokens & context_tokens) / len(response_tokens)
        score = round(1.0 - support, 12)
        label = (
            HallucinationLabel.GROUNDED
            if support >= self.overlap_threshold
            else HallucinationLabel.HALLUCINATED
        )
        return HallucinationPrediction(
            example_id=example_id,
            label=label,
            score=score,
            evaluator_name=self.name,
            evaluator_version=self.version,
            evaluator_config=self.config,
        )
