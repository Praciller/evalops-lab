"""Small deterministic BM25 baseline with Thai-aware character n-grams."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable

from evalops.models.retrieval import CorpusDocument, RetrievalQuery
from evalops.retrieval.base import RetrievedDocument

THAI_RUN = re.compile(r"[\u0e00-\u0e7f]+")
LATIN_OR_NUMBER_RUN = re.compile(r"[a-z]+|\d+(?:[.,]\d+)?")


def tokenize_thai_aware(text: str) -> list[str]:
    """Tokenize Thai with overlapping code-point n-grams and other scripts as runs.

    Thai does not use whitespace between words reliably.  Character bigrams and
    trigrams avoid pretending that English whitespace tokenization applies to
    Thai while keeping this baseline dependency-light and reproducible.
    """

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    cursor = 0
    for match in re.finditer(r"[\u0e00-\u0e7f]+|[a-z]+|\d+(?:[.,]\d+)?", normalized):
        cursor = match.end()
        segment = match.group(0)
        if THAI_RUN.fullmatch(segment):
            if len(segment) < 2:
                tokens.append(segment)
            else:
                tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
                if len(segment) >= 3:
                    tokens.extend(segment[index : index + 3] for index in range(len(segment) - 2))
        else:
            tokens.append(segment)
    if cursor == 0:
        return []
    return tokens


class BM25Retriever:
    """In-memory BM25 retriever for smoke and explicitly opt-in local runs."""

    name = "bm25"
    version = "bm25-local-v1"
    tokenization_strategy = "unicode_thai_character_bigrams_trigrams_plus_latin_runs"

    def __init__(
        self,
        documents: Iterable[CorpusDocument],
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 parameters require k1 > 0 and 0 <= b <= 1")
        self.k1 = k1
        self.b = b
        self._documents: dict[str, CorpusDocument] = {}
        self._postings: dict[str, dict[str, int]] = defaultdict(dict)
        self._document_lengths: dict[str, int] = {}
        for document in documents:
            if document.document_id in self._documents:
                raise ValueError(f"duplicate document ID '{document.document_id}'")
            self._documents[document.document_id] = document
            counts = Counter(tokenize_thai_aware(f"{document.title} {document.text}"))
            length = sum(counts.values())
            self._document_lengths[document.document_id] = length
            for token, frequency in counts.items():
                self._postings[token][document.document_id] = frequency
        self._average_document_length = (
            sum(self._document_lengths.values()) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RetrievedDocument]:
        """Return unique results ranked by score, then document ID for ties."""

        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        query_tokens = set(tokenize_thai_aware(query.text))
        if not query_tokens or not self._documents:
            return []

        scores: dict[str, float] = defaultdict(float)
        document_count = len(self._documents)
        for token in query_tokens:
            postings = self._postings.get(token)
            if not postings:
                continue
            document_frequency = len(postings)
            inverse_document_frequency = math.log1p(
                (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            for document_id, term_frequency in postings.items():
                document_length = self._document_lengths[document_id]
                normalization = self.k1 * (
                    1 - self.b + self.b * document_length / self._average_document_length
                )
                scores[document_id] += inverse_document_frequency * (
                    term_frequency * (self.k1 + 1) / (term_frequency + normalization)
                )

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        return [
            RetrievedDocument(document_id=document_id, score=score, rank=rank)
            for rank, (document_id, score) in enumerate(ranked, start=1)
        ]
