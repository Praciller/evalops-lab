"""Generic retriever contract shared by benchmark adapters."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from evalops.models.retrieval import RetrievalQuery


class RetrievedDocument(BaseModel):
    """One ranked result emitted by a retriever."""

    document_id: str
    score: float
    rank: int


class Retriever(Protocol):
    """Minimal interface for plugging different retrievers into a benchmark."""

    name: str
    version: str
    tokenization_strategy: str

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RetrievedDocument]: ...
