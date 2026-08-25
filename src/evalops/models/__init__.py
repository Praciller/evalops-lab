"""Structured models shared by EvalOps Lab components."""

from evalops.models.datasets import (
    DatasetCategory,
    DatasetValidationIssue,
    DatasetValidationReport,
    Difficulty,
    RAGCase,
)
from evalops.models.retrieval import (
    CorpusDocument,
    RelevanceJudgment,
    RetrievalPrediction,
    RetrievalQuery,
)
from evalops.models.runs import EvaluationResult, RunConfig

__all__ = [
    "DatasetCategory",
    "DatasetValidationIssue",
    "DatasetValidationReport",
    "Difficulty",
    "RAGCase",
    "CorpusDocument",
    "RelevanceJudgment",
    "RetrievalPrediction",
    "RetrievalQuery",
    "EvaluationResult",
    "RunConfig",
]
