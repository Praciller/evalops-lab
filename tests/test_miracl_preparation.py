from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from evalops.datasets.miracl_prepare import (
    MIRACL_CORPUS_REVISION,
    MIRACL_TOPICS_QRELS_REVISION,
    default_miracl_sources,
    prepare_miracl,
)


def test_default_sources_are_pinned_to_verified_upstream_revisions() -> None:
    sources = default_miracl_sources("th", "dev")

    assert MIRACL_TOPICS_QRELS_REVISION in sources.topics
    assert MIRACL_TOPICS_QRELS_REVISION in sources.qrels
    assert MIRACL_CORPUS_REVISION in sources.corpus[0]
    assert sources.topics.endswith("topics.miracl-v1.0-th-dev.tsv")
    assert sources.qrels.endswith("qrels.miracl-v1.0-th-dev.tsv")


def test_mini_preparation_is_offline_and_reports_fixture_counts() -> None:
    summary = prepare_miracl(
        language="th",
        split="dev",
        output_dir=Path("datasets/external/miracl/th/dev"),
        mini=True,
        fixture_dir=Path("datasets/fixtures/miracl-th-mini"),
    )

    assert summary.mode == "mini"
    assert summary.queries == 5
    assert summary.qrels == 11
    assert summary.corpus_documents == 6
    assert summary.output_paths[0].endswith("topics.tsv")


def test_local_preparation_is_idempotent_and_can_skip_corpus(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    topics = source_dir / "topics.tsv"
    qrels = source_dir / "qrels.tsv"
    corpus = source_dir / "docs-0.jsonl.gz"
    topics.write_text("1\tคำถาม\n", encoding="utf-8")
    qrels.write_text("1 Q0 d1 1\n", encoding="utf-8")
    with gzip.open(corpus, "wt", encoding="utf-8") as handle:
        handle.write('{"docid":"d1","title":"ชื่อ","text":"ข้อความ"}\n')

    output_dir = tmp_path / "prepared"
    first = prepare_miracl(
        language="th",
        split="dev",
        output_dir=output_dir,
        topics_source=str(topics),
        qrels_source=str(qrels),
        corpus_source=str(source_dir),
    )
    second = prepare_miracl(
        language="th",
        split="dev",
        output_dir=output_dir,
        topics_source=str(topics),
        qrels_source=str(qrels),
        corpus_source=str(source_dir),
    )

    assert first.queries == second.queries == 1
    assert first.corpus_documents == second.corpus_documents == 1


def test_preparation_rejects_duplicate_documents_across_corpus_shards(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "topics.tsv").write_text("1\tคำถาม\n", encoding="utf-8")
    (source_dir / "qrels.tsv").write_text("1 Q0 d1 1\n", encoding="utf-8")
    for shard in ("docs-0.jsonl.gz", "docs-1.jsonl.gz"):
        with gzip.open(source_dir / shard, "wt", encoding="utf-8") as handle:
            handle.write('{"docid":"d1","title":"ชื่อ","text":"ข้อความ"}\n')

    with pytest.raises(ValueError, match="duplicate document ID"):
        prepare_miracl(
            language="th",
            split="dev",
            output_dir=tmp_path / "prepared",
            topics_source=str(source_dir / "topics.tsv"),
            qrels_source=str(source_dir / "qrels.tsv"),
            corpus_source=str(source_dir),
        )
