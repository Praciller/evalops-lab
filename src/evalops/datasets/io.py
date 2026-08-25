"""Safe, explicit readers for benchmark JSONL inputs."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from evalops.models.retrieval import RetrievalGroundTruth, RetrievalPrediction

ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_unique_query_records(
    path: str | Path,
    model_type: type[ModelT],
    query_id_getter: Callable[[ModelT], str],
) -> list[ModelT]:
    records: list[ModelT] = []
    seen_query_ids: set[str] = set()
    file_path = Path(path)
    with file_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = model_type.model_validate(json.loads(line))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
                raise ValueError(
                    f"could not parse {file_path} line {line_number}: {error}"
                ) from error
            query_id = query_id_getter(record)
            if query_id in seen_query_ids:
                raise ValueError(
                    f"duplicate query_id '{query_id}' in {file_path} line {line_number}"
                )
            seen_query_ids.add(query_id)
            records.append(record)
    return records


def load_retrieval_ground_truth(path: str | Path) -> dict[str, list[str]]:
    """Load query-to-relevant-document mappings."""

    records = _load_unique_query_records(path, RetrievalGroundTruth, lambda record: record.query_id)
    return {record.query_id: record.relevant_document_ids for record in records}


def load_retrieval_predictions(path: str | Path) -> dict[str, list[str]]:
    """Load query-to-ranked-document mappings."""

    records = _load_unique_query_records(path, RetrievalPrediction, lambda record: record.query_id)
    return {record.query_id: record.retrieved_document_ids for record in records}
