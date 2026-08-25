"""Interfaces for model-dependent generation evaluation."""

from evalops.evaluators.generation.interface import (
    ContextDocument,
    GenerationEvaluation,
    GenerationEvaluator,
)

__all__ = ["ContextDocument", "GenerationEvaluation", "GenerationEvaluator"]
