"""Generate the checked-in, synthetic Evidence Console demo bundle.

This script is intentionally explicit: it runs only the two local fixtures named
below and writes only their two run artifacts plus the explicit index. It never
scans a reports directory, downloads data, calls a provider, or publishes raw
evaluation details.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPOSITORY_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evalops.benchmarks.miracl import run_miracl_benchmark  # noqa: E402
from evalops.export import (  # noqa: E402
    ClaimScope,
    DataKind,
    VerificationStatus,
    adapt_evaluation_result,
    build_public_index,
    write_public_artifact,
)
from evalops.models.runs import RunConfig  # noqa: E402
from evalops.runners.retrieval import run_retrieval_evaluation  # noqa: E402

FIXED_TIMESTAMP = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
EVIDENCE_DIR = REPOSITORY_ROOT / "apps" / "web" / "public" / "evidence"

RETRIEVAL_ARTIFACT_ID = "demo-retrieval-fixture-v1"
MIRACL_ARTIFACT_ID = "demo-miracl-th-mini-v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _retrieval_result() -> Any:
    ground_truth_rows = _read_jsonl(
        REPOSITORY_ROOT / "datasets" / "fixtures" / "retrieval-ground-truth.jsonl"
    )
    prediction_rows = _read_jsonl(
        REPOSITORY_ROOT / "datasets" / "fixtures" / "retrieval-predictions.jsonl"
    )
    ground_truth = {row["query_id"]: row["relevant_document_ids"] for row in ground_truth_rows}
    predictions = {row["query_id"]: row["retrieved_document_ids"] for row in prediction_rows}
    result = run_retrieval_evaluation(
        ground_truth,
        predictions,
        RunConfig(
            run_id=RETRIEVAL_ARTIFACT_ID,
            dataset_name="retrieval-fixture",
            dataset_version="synthetic-v1",
            dataset_revision="checked-in-fixture-v1",
            system_name="fixture-predictions",
            top_k=5,
            evaluator_versions={"retrieval": "deterministic-metrics-v1"},
            timestamp=FIXED_TIMESTAMP,
        ),
    )
    public_per_query = {}
    for query_id, query_result in result.details["per_query"].items():
        public_per_query[query_id] = {
            "metrics": query_result.metrics,
            "failure_category": query_result.failure_category.value,
            "retrieved_document_ids": list(predictions.get(query_id, [])),
            "relevant_document_ids": list(ground_truth.get(query_id, [])),
        }
    return result.model_copy(update={"details": {"per_query": public_per_query}})


def _miracl_result() -> Any:
    fixture_dir = REPOSITORY_ROOT / "datasets" / "fixtures" / "miracl-th-mini"
    return run_miracl_benchmark(
        topics_path=fixture_dir / "topics.tsv",
        qrels_path=fixture_dir / "qrels.tsv",
        corpus_paths=[fixture_dir / "corpus.jsonl"],
        config=RunConfig(
            run_id=MIRACL_ARTIFACT_ID,
            dataset_name="miracl-th-mini",
            dataset_version="synthetic-fixture-v1",
            dataset_revision="synthetic-fixture-v1",
            system_name="evalops-bm25-mini",
            benchmark="miracl",
            language="th",
            split="dev",
            retriever="bm25",
            retriever_version="bm25-local-v1",
            tokenization_strategy="thai-character-bigrams-trigrams-latin-runs",
            top_k=5,
            evaluator_versions={"retrieval": "deterministic-metrics-v1"},
            timestamp=FIXED_TIMESTAMP,
        ),
    )


def generate(output_dir: Path = EVIDENCE_DIR) -> None:
    """Write the deterministic public bundle to one explicit output directory."""

    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    common = {
        "verification_status": VerificationStatus.VERIFIED,
        "data_kind": DataKind.SYNTHETIC_FIXTURE,
        "claim_scope": ClaimScope.INTEGRATION_ONLY,
    }
    retrieval = adapt_evaluation_result(
        _retrieval_result(),
        artifact_id=RETRIEVAL_ARTIFACT_ID,
        limitations=[
            "Synthetic retrieval fixture only; not a production workload or generalization claim.",
            (
                "Metrics are deterministic fixture evidence with no external model or provider "
                "inference."
            ),
        ],
        **common,
    )
    miracl = adapt_evaluation_result(
        _miracl_result(),
        artifact_id=MIRACL_ARTIFACT_ID,
        limitations=[
            (
                "Synthetic MIRACL-shaped Thai mini fixture; not official MIRACL benchmark data "
                "or a leaderboard result."
            ),
            "BM25 is a local deterministic baseline; no model-superiority claim is supported.",
        ],
        **common,
    )
    index = build_public_index([retrieval, miracl])
    write_public_artifact(retrieval, artifacts_dir / f"{retrieval.artifact_id}.json")
    write_public_artifact(miracl, artifacts_dir / f"{miracl.artifact_id}.json")
    write_public_artifact(index, output_dir / "index.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE_DIR)
    args = parser.parse_args()
    generate(args.output_dir.resolve())


if __name__ == "__main__":
    main()
