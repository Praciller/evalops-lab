"""Evaluator protocol shared by local and future hallucination detectors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from evalops.models.hallucination import HallucinationPrediction


class HallucinationEvaluator(Protocol):
    """Minimal context/response interface for interchangeable evaluators."""

    name: str
    version: str

    @property
    def config(self) -> Mapping[str, Any]: ...

    def evaluate(
        self, context: str, response: str, *, example_id: str = ""
    ) -> HallucinationPrediction: ...
