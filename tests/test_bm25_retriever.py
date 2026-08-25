from __future__ import annotations

import pytest

from evalops.models.retrieval import CorpusDocument, RetrievalQuery
from evalops.retrieval.bm25 import BM25Retriever, tokenize_thai_aware


def _document(document_id: str, text: str, title: str = "") -> CorpusDocument:
    return CorpusDocument(document_id=document_id, title=title, text=text)


def test_thai_aware_tokenizer_produces_non_empty_character_ngrams() -> None:
    tokens = tokenize_thai_aware("กรุงเทพมหานคร มีประชากร 10 คน")

    assert "กร" in tokens
    assert "กรุงเทพมหานคร" not in tokens
    assert "10" in tokens


def test_bm25_ranks_exact_thai_match_before_partial_and_irrelevant_text() -> None:
    retriever = BM25Retriever(
        [
            _document("d1", "กรุงเทพมหานครเป็นเมืองหลวงของประเทศไทย"),
            _document("d2", "ประเทศไทยมีหลายจังหวัดและเมืองสำคัญ"),
            _document("d3", "แม่น้ำโขงไหลผ่านหลายประเทศ"),
        ]
    )

    results = retriever.retrieve(RetrievalQuery(query_id="q1", text="กรุงเทพมหานคร"), top_k=3)

    assert results[0].document_id == "d1"
    assert len({result.document_id for result in results}) == len(results)
    assert all(
        results[index].score >= results[index + 1].score for index in range(len(results) - 1)
    )
    assert results[0].score > 0
    assert results[0].rank == 1


def test_bm25_tie_breaking_is_stable_by_document_id() -> None:
    retriever = BM25Retriever([_document("d2", "แม่น้ำ"), _document("d1", "แม่น้ำ")])

    results = retriever.retrieve(RetrievalQuery(query_id="q1", text="แม่น้ำ"), top_k=2)

    assert [result.document_id for result in results] == ["d1", "d2"]


def test_empty_query_returns_no_results_and_top_k_is_validated() -> None:
    retriever = BM25Retriever([_document("d1", "ข้อความ")])

    assert retriever.retrieve(RetrievalQuery(query_id="q1", text="   "), top_k=5) == []
    with pytest.raises(ValueError, match="top_k must be a positive integer"):
        retriever.retrieve(RetrievalQuery(query_id="q1", text="ข้อความ"), top_k=0)


def test_duplicate_corpus_document_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate document ID"):
        BM25Retriever([_document("d1", "one"), _document("d1", "two")])
