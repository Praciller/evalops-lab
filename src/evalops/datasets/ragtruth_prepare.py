"""Pinned, checksum-aware preparation for the official RAGTruth JSONL files."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from pydantic import BaseModel, Field

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.models.hallucination import AnnotationPolicy

RAGTRUTH_REVISION = "c103204b9ce28d6bbad859304bf30de72b8ed8fe"
RAGTRUTH_RESPONSE_URL = (
    f"https://raw.githubusercontent.com/ParticleMedia/RAGTruth/{RAGTRUTH_REVISION}/"
    "dataset/response.jsonl"
)
RAGTRUTH_SOURCE_INFO_URL = (
    f"https://raw.githubusercontent.com/ParticleMedia/RAGTruth/{RAGTRUTH_REVISION}/"
    "dataset/source_info.jsonl"
)


class RAGTruthPreparationSummary(BaseModel):
    """Serializable provenance and validation summary for a prepared snapshot."""

    dataset: str = "ragtruth"
    mode: str
    source_revision: str
    responses: int
    sources: int
    hallucination_responses: int
    hallucination_spans: int
    split_counts: dict[str, int] = Field(default_factory=dict)
    quality_counts: dict[str, int] = Field(default_factory=dict)
    output_paths: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)
    validation_issues: int = 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_source(source: str, destination: Path, expected_sha256: str | None = None) -> str:
    if destination.exists():
        existing = _sha256_file(destination)
        if expected_sha256 and existing == expected_sha256:
            return existing
        if Path(source).is_file() and existing == _sha256_file(Path(source)):
            return existing
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
    checksum = _sha256_file(destination)
    if expected_sha256 and checksum != expected_sha256:
        destination.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch: expected {expected_sha256}, got {checksum}")
    return checksum


def _summary(
    response_path: Path,
    source_info_path: Path,
    *,
    mode: str,
    source_revision: str,
    output_paths: list[str],
    checksums: dict[str, str],
) -> RAGTruthPreparationSummary:
    dataset = load_ragtruth_dataset(
        response_path, source_info_path, source_revision=source_revision
    )
    split_counts: dict[str, int] = {}
    for example in dataset.examples:
        split_counts[example.split] = split_counts.get(example.split, 0) + 1
    return RAGTruthPreparationSummary(
        mode=mode,
        source_revision=source_revision,
        responses=len(dataset.examples),
        sources=len({example.source_id for example in dataset.examples}),
        hallucination_responses=sum(
            example.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS).value == "HALLUCINATED"
            for example in dataset.examples
        ),
        hallucination_spans=sum(len(example.spans) for example in dataset.examples),
        split_counts=dict(sorted(split_counts.items())),
        quality_counts=dataset.quality_counts,
        output_paths=output_paths,
        checksums=checksums,
        validation_issues=len(dataset.validation_issues),
    )


def prepare_ragtruth(
    *,
    output_dir: str | Path,
    mini: bool = False,
    fixture_dir: str | Path | None = None,
    response_source: str | None = None,
    source_info_source: str | None = None,
    expected_response_sha256: str | None = None,
    expected_source_sha256: str | None = None,
) -> RAGTruthPreparationSummary:
    """Prepare either the committed synthetic fixture or pinned official files."""

    if mini:
        root = Path(fixture_dir or "datasets/fixtures/ragtruth-mini")
        return _summary(
            root / "response.jsonl",
            root / "source_info.jsonl",
            mode="mini",
            source_revision="synthetic-fixture-v1",
            output_paths=[str(root / "response.jsonl"), str(root / "source_info.jsonl")],
            checksums={
                "response.jsonl": _sha256_file(root / "response.jsonl"),
                "source_info.jsonl": _sha256_file(root / "source_info.jsonl"),
            },
        )

    root = Path(output_dir)
    response_path = root / "response.jsonl"
    source_info_path = root / "source_info.jsonl"
    response_checksum = _copy_source(
        response_source or RAGTRUTH_RESPONSE_URL,
        response_path,
        expected_sha256=expected_response_sha256,
    )
    source_checksum = _copy_source(
        source_info_source or RAGTRUTH_SOURCE_INFO_URL,
        source_info_path,
        expected_sha256=expected_source_sha256,
    )
    summary = _summary(
        response_path,
        source_info_path,
        mode="full-prepared",
        source_revision=RAGTRUTH_REVISION,
        output_paths=["response.jsonl", "source_info.jsonl"],
        checksums={"response.jsonl": response_checksum, "source_info.jsonl": source_checksum},
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "preparation-manifest.json").write_text(
        summary.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return summary
