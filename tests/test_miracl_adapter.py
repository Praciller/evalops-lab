from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from evalops.datasets.miracl import (
    load_miracl_qrels,
    load_miracl_topics,
    validate_miracl_records,
)
from evalops.models.retrieval import RetrievalPrediction


def test_topics_and_qrels_parse_to_normalized_records(tmp_path: Path) -> None:
    topics = tmp_path / "topics.tsv"
    qrels = tmp_path / "qrels.tsv"
    topics.write_text("1\tกรุงเทพมหานครอยู่ที่ใด\n2\tแม่น้ำสำคัญคืออะไร\n", encoding="utf-8")
    qrels.write_text("1 Q0 d1 2\n1 Q0 d2 0\n2 Q0 d2 1\n", encoding="utf-8")

    parsed_topics = load_miracl_topics(topics)
    parsed_qrels = load_miracl_qrels(qrels)

    assert parsed_topics[0].query_id == "1"
    assert parsed_topics[0].text == "กรุงเทพมหานครอยู่ที่ใด"
    assert parsed_qrels["1"] == {"d1": 2, "d2": 0}


@pytest.mark.parametrize("contents", ["1 only-one-column\n", "\tmissing-id\n", "1\t\n"])
def test_malformed_topic_is_rejected(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "topics.tsv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="topics.tsv line 1"):
        load_miracl_topics(path)


@pytest.mark.parametrize("contents", ["1 Q0 d1\n", "1 Q1 d1 1\n", "1 Q0 d1 nope\n"])
def test_malformed_qrel_is_rejected(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "qrels.tsv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="qrels.tsv line 1"):
        load_miracl_qrels(path)


def test_duplicate_ids_and_unknown_references_are_reported() -> None:
    topics = load_miracl_topics_from_text("1\tคำถามหนึ่ง\n1\tคำถามซ้ำ\n")
    qrels = {"missing": {"d1": 1}, "1": {"missing-doc": 1}}

    report = validate_miracl_records(topics, qrels, corpus_document_ids={"d1"})

    assert not report.valid
    assert {issue.code for issue in report.issues} == {
        "DUPLICATE_QUERY_ID",
        "UNKNOWN_QUERY_ID",
        "UNKNOWN_CORPUS_DOCUMENT_ID",
    }


def test_corpus_unicode_text_round_trips_through_gzip(tmp_path: Path) -> None:
    path = tmp_path / "docs.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"docid": "d1", "title": "ภาษาไทย", "text": "ข้อความไทย"}) + "\n")

    from evalops.datasets.miracl import iter_miracl_corpus

    documents = list(iter_miracl_corpus(path))

    assert documents[0].document_id == "d1"
    assert documents[0].title == "ภาษาไทย"
    assert documents[0].text == "ข้อความไทย"


def test_prediction_model_rejects_duplicate_documents_and_misaligned_scores() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        RetrievalPrediction(query_id="q1", retrieved_document_ids=["d1", "d1"])
    with pytest.raises(ValueError, match="same length"):
        RetrievalPrediction(query_id="q1", retrieved_document_ids=["d1"], scores=[])


def load_miracl_topics_from_text(contents: str):
    """Test helper that keeps the adapter test focused on public validation behavior."""

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".tsv", delete=False
    ) as handle:
        handle.write(contents)
        path = Path(handle.name)
    try:
        return load_miracl_topics(path)
    finally:
        path.unlink()
