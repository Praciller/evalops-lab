"""Normalized retrieval benchmark contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalQuery(BaseModel):
    """A query independent of any upstream benchmark format."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class CorpusDocument(BaseModel):
    """A passage in a retrieval corpus."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    title: str = ""
    text: str = Field(min_length=1)


class RelevanceJudgment(BaseModel):
    """One TREC-style query/document relevance label."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    relevance: int = Field(ge=0)


class RetrievalGroundTruth(BaseModel):
    """Relevant document IDs supplied by human or benchmark ground truth."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    relevant_document_ids: list[str] = Field(default_factory=list)


class RetrievalPrediction(BaseModel):
    """Document ranking returned by the system under evaluation."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    retrieved_document_ids: list[str] = Field(default_factory=list)
    scores: list[float] | None = None

    @model_validator(mode="after")
    def validate_ranking(self) -> RetrievalPrediction:
        if len(self.retrieved_document_ids) != len(set(self.retrieved_document_ids)):
            raise ValueError("retrieved_document_ids must not contain duplicates")
        if self.scores is not None and len(self.scores) != len(self.retrieved_document_ids):
            raise ValueError("scores must have the same length as retrieved_document_ids")
        return self
