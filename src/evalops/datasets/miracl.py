"""MIRACL TSV/qrels/corpus adapter into stable EvalOps models."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from evalops.models.datasets import DatasetValidationIssue, DatasetValidationReport
from evalops.models.retrieval import CorpusDocument, RelevanceJudgment, RetrievalQuery


def _open_text(path: str | Path) -> TextIO:
    file_path = Path(path)
    if file_path.suffix == ".gz":
        return gzip.open(file_path, "rt", encoding="utf-8")
    return file_path.open(encoding="utf-8")


def load_miracl_topics(path: str | Path) -> list[RetrievalQuery]:
    """Parse MIRACL's ``qid<TAB>query`` topic format."""

    topics: list[RetrievalQuery] = []
    file_path = Path(path)
    with _open_text(file_path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            fields = line.split("\t", maxsplit=1)
            if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: expected qid<TAB>query"
                )
            try:
                topics.append(RetrievalQuery(query_id=fields[0].strip(), text=fields[1].strip()))
            except ValidationError as error:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: {error}"
                ) from error
    return topics


def load_miracl_qrels(path: str | Path) -> dict[str, dict[str, int]]:
    """Parse standard four-column MIRACL/TREC qrels."""

    qrels: dict[str, dict[str, int]] = {}
    file_path = Path(path)
    with _open_text(file_path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            fields = line.split()
            if len(fields) != 4 or fields[1] != "Q0":
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: "
                    "expected qid Q0 docid relevance"
                )
            query_id, _, document_id, relevance_text = fields
            try:
                relevance = int(relevance_text)
            except ValueError as error:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: "
                    "relevance must be an integer"
                ) from error
            if relevance < 0:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: "
                    "relevance must be non-negative"
                )
            judgment = RelevanceJudgment(
                query_id=query_id,
                document_id=document_id,
                relevance=relevance,
            )
            query_qrels = qrels.setdefault(judgment.query_id, {})
            if judgment.document_id in query_qrels:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: duplicate qrel"
                )
            query_qrels[judgment.document_id] = judgment.relevance
    return qrels


def iter_miracl_corpus(path: str | Path) -> Iterator[CorpusDocument]:
    """Stream MIRACL JSONL/JSONL.GZ passages without duplicating the corpus."""

    file_path = Path(path)
    seen_document_ids: set[str] = set()
    with _open_text(file_path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
                document = CorpusDocument(
                    document_id=record["docid"],
                    title=record.get("title", ""),
                    text=record["text"],
                )
            except (
                KeyError,
                json.JSONDecodeError,
                TypeError,
                ValidationError,
                ValueError,
            ) as error:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: {error}"
                ) from error
            if document.document_id in seen_document_ids:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: "
                    f"duplicate document ID '{document.document_id}'"
                )
            seen_document_ids.add(document.document_id)
            yield document


def validate_miracl_records(
    topics: Sequence[RetrievalQuery],
    qrels: Mapping[str, Mapping[str, int]],
    *,
    corpus_document_ids: set[str] | None = None,
) -> DatasetValidationReport:
    """Validate topic uniqueness and qrel references without changing labels."""

    issues: list[DatasetValidationIssue] = []
    seen_query_ids: set[str] = set()
    for topic in topics:
        if topic.query_id in seen_query_ids:
            issues.append(
                DatasetValidationIssue(
                    code="DUPLICATE_QUERY_ID",
                    message=f"query ID '{topic.query_id}' occurs more than once",
                    record_id=topic.query_id,
                )
            )
        seen_query_ids.add(topic.query_id)

    for query_id, query_qrels in qrels.items():
        if query_id not in seen_query_ids:
            issues.append(
                DatasetValidationIssue(
                    code="UNKNOWN_QUERY_ID",
                    message=f"qrels reference unknown query ID '{query_id}'",
                    record_id=query_id,
                )
            )
        for document_id, relevance in query_qrels.items():
            if relevance < 0:
                issues.append(
                    DatasetValidationIssue(
                        code="INVALID_RELEVANCE",
                        message="relevance must be non-negative",
                        record_id=f"{query_id}:{document_id}",
                    )
                )
            if corpus_document_ids is not None and document_id not in corpus_document_ids:
                issues.append(
                    DatasetValidationIssue(
                        code="UNKNOWN_CORPUS_DOCUMENT_ID",
                        message=f"qrels reference unknown corpus document '{document_id}'",
                        record_id=f"{query_id}:{document_id}",
                    )
                )

    return DatasetValidationReport(
        valid=not issues,
        records_checked=len(topics),
        issues=issues,
    )
