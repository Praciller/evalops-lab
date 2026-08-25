"""Pinned, auditable MIRACL source preparation without remote code execution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from pydantic import BaseModel, Field

from evalops.datasets.miracl import (
    iter_miracl_corpus,
    load_miracl_qrels,
    load_miracl_topics,
    validate_miracl_records,
)

MIRACL_TOPICS_QRELS_REVISION = "5be20db9509754dadad47689368639fcec739c00"
MIRACL_CORPUS_REVISION = "d921ec7e349ce0d28daf30b2da9da5ee698bef0d"
MIRACL_CORPUS_SHARDS = {"th": 2}


@dataclass(frozen=True)
class MiraclSources:
    """Immutable source URLs for a pinned language/split."""

    topics: str
    qrels: str
    corpus: tuple[str, ...]


class MiraclPreparationSummary(BaseModel):
    """Serializable summary emitted by preparation commands."""

    dataset: str = "miracl"
    language: str
    split: str
    mode: str
    queries: int
    qrels: int
    corpus_documents: int | None
    source_revision: str
    output_paths: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)


def _canonical_split(split: str) -> str:
    normalized = split.casefold().replace("-", "")
    aliases = {"train": "train", "dev": "dev", "testa": "testA", "testb": "testB"}
    if normalized not in aliases:
        raise ValueError("MIRACL split must be one of: train, dev, testA, testB")
    return aliases[normalized]


def default_miracl_sources(language: str, split: str) -> MiraclSources:
    """Return pinned direct artifacts documented by the official MIRACL sources."""

    language = language.casefold()
    canonical_split = _canonical_split(split)
    if language != "th":
        raise ValueError("Phase 2 supports only MIRACL language 'th'")
    if canonical_split not in {"train", "dev"}:
        raise ValueError("MIRACL topics/qrels preparation currently supports train and dev")
    split_suffix = canonical_split.casefold()
    base_topics = (
        "https://huggingface.co/datasets/miracl/miracl/resolve/"
        f"{MIRACL_TOPICS_QRELS_REVISION}/miracl-v1.0-{language}"
    )
    base_corpus = (
        "https://huggingface.co/datasets/miracl/miracl-corpus/resolve/"
        f"{MIRACL_CORPUS_REVISION}/miracl-corpus-v1.0-{language}"
    )
    return MiraclSources(
        topics=f"{base_topics}/topics/topics.miracl-v1.0-{language}-{split_suffix}.tsv",
        qrels=f"{base_topics}/qrels/qrels.miracl-v1.0-{language}-{split_suffix}.tsv",
        corpus=tuple(
            f"{base_corpus}/docs-{shard}.jsonl.gz"
            for shard in range(MIRACL_CORPUS_SHARDS[language])
        ),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_source(
    source: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
) -> str:
    """Copy one local/HTTPS source using a temporary sibling and stable checksum."""

    if destination.exists():
        existing_checksum = _sha256_file(destination)
        if expected_sha256 and existing_checksum == expected_sha256:
            return existing_checksum
        if Path(source).is_file() and existing_checksum == _sha256_file(Path(source)):
            return existing_checksum
        raise FileExistsError(
            f"destination already exists with different or unverifiable content: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        try:
            if urlparse(source).scheme in {"http", "https"}:
                with urlopen(source, timeout=120) as response:  # noqa: S310 - pinned source URL
                    shutil.copyfileobj(response, handle)
            else:
                source_path = Path(source)
                if not source_path.is_file():
                    raise FileNotFoundError(f"source does not exist: {source_path}")
                with source_path.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, destination)
    return _sha256_file(destination)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_preparation_manifest(root: Path, summary: MiraclPreparationSummary) -> None:
    manifest = root / "preparation-manifest.json"
    manifest.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _previous_checksums(root: Path) -> dict[str, str]:
    manifest = root / "preparation-manifest.json"
    if not manifest.is_file():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    checksums = payload.get("checksums", {})
    return checksums if isinstance(checksums, dict) else {}


def prepare_miracl(
    *,
    language: str,
    split: str,
    output_dir: str | Path,
    mini: bool = False,
    fixture_dir: str | Path | None = None,
    topics_source: str | None = None,
    qrels_source: str | None = None,
    corpus_source: str | None = None,
    topics_qrels_only: bool = False,
) -> MiraclPreparationSummary:
    """Prepare MIRACL topics/qrels and optionally corpus shards.

    The mini mode reads only the committed synthetic fixture. Full mode uses
    immutable direct file URLs by default or explicit local source overrides.
    """

    language = language.casefold()
    canonical_split = _canonical_split(split)
    if mini:
        fixture_root = Path(fixture_dir or "datasets/fixtures/miracl-th-mini")
        topics_path = fixture_root / "topics.tsv"
        qrels_path = fixture_root / "qrels.tsv"
        corpus_path = fixture_root / "corpus.jsonl"
        topics = load_miracl_topics(topics_path)
        qrels = load_miracl_qrels(qrels_path)
        documents = list(iter_miracl_corpus(corpus_path))
        validation = validate_miracl_records(
            topics, qrels, corpus_document_ids={document.document_id for document in documents}
        )
        if not validation.valid:
            raise ValueError("synthetic MIRACL fixture failed validation")
        return MiraclPreparationSummary(
            language=language,
            split=canonical_split,
            mode="mini",
            queries=len(topics),
            qrels=sum(len(query_qrels) for query_qrels in qrels.values()),
            corpus_documents=len(documents),
            source_revision="synthetic-fixture-v1",
            output_paths=[str(topics_path), str(qrels_path), str(corpus_path)],
            checksums={
                path.name: _sha256_file(path) for path in (topics_path, qrels_path, corpus_path)
            },
        )

    sources = default_miracl_sources(language, canonical_split)
    root = Path(output_dir)
    previous_checksums = _previous_checksums(root)
    topics_path = root / "topics.tsv"
    qrels_path = root / "qrels.tsv"
    topics_checksum = _copy_source(
        topics_source or sources.topics,
        topics_path,
        expected_sha256=previous_checksums.get("topics.tsv"),
    )
    qrels_checksum = _copy_source(
        qrels_source or sources.qrels,
        qrels_path,
        expected_sha256=previous_checksums.get("qrels.tsv"),
    )
    corpus_paths: list[Path] = []
    corpus_checksums: dict[str, str] = {}
    if not topics_qrels_only:
        corpus_root = root / "corpus"
        source_path = (
            Path(corpus_source) if corpus_source and Path(corpus_source).exists() else None
        )
        if source_path is not None and source_path.is_dir():
            source_files = sorted(source_path.glob("*.jsonl.gz"))
            if not source_files:
                raise FileNotFoundError(f"no .jsonl.gz corpus shards found in {source_path}")
            corpus_sources = [str(path) for path in source_files]
        elif source_path is not None:
            corpus_sources = [str(source_path)]
        else:
            corpus_sources = list(sources.corpus)
        for shard_index, source in enumerate(corpus_sources):
            destination = corpus_root / Path(urlparse(source).path).name
            if destination.name in {"", "."}:
                destination = corpus_root / f"docs-{shard_index}.jsonl.gz"
            corpus_paths.append(destination)
            relative_destination = _relative(destination, root)
            corpus_checksums[relative_destination] = _copy_source(
                source,
                destination,
                expected_sha256=previous_checksums.get(relative_destination),
            )

    topics = load_miracl_topics(topics_path)
    qrels = load_miracl_qrels(qrels_path)
    corpus_documents: int | None = None
    if corpus_paths:
        corpus_ids: set[str] = set()
        for corpus_path in corpus_paths:
            for document in iter_miracl_corpus(corpus_path):
                if document.document_id in corpus_ids:
                    raise ValueError(
                        f"MIRACL corpus contains duplicate document ID '{document.document_id}'"
                    )
                corpus_ids.add(document.document_id)
        corpus_documents = len(corpus_ids)
    validation = validate_miracl_records(
        topics,
        qrels,
        corpus_document_ids=corpus_ids if corpus_paths else None,
    )
    if not validation.valid:
        issue_text = "; ".join(f"{issue.code}: {issue.message}" for issue in validation.issues)
        raise ValueError(f"MIRACL validation failed: {issue_text}")

    summary = MiraclPreparationSummary(
        language=language,
        split=canonical_split,
        mode="full-prepared",
        queries=len(topics),
        qrels=sum(len(query_qrels) for query_qrels in qrels.values()),
        corpus_documents=corpus_documents,
        source_revision=(
            f"topics_qrels:{MIRACL_TOPICS_QRELS_REVISION}; corpus:{MIRACL_CORPUS_REVISION}"
        ),
        output_paths=[
            _relative(topics_path, root),
            _relative(qrels_path, root),
            *[_relative(path, root) for path in corpus_paths],
        ],
        checksums={
            "topics.tsv": topics_checksum,
            "qrels.tsv": qrels_checksum,
            **corpus_checksums,
        },
    )
    root.mkdir(parents=True, exist_ok=True)
    _write_preparation_manifest(root, summary)
    return summary
