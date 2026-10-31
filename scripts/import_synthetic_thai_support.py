"""Convert the *synthetic* Thai Support RAG evaluation to EvalOps retrieval JSONL.

This is a local opt-in adapter. It deliberately refuses unidentified or private
artifacts and never uploads, prints query text, or calls an external service.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DATASET_ID = "synthetic-thai-enterprise-policy-v1"
MODE = "offline_character_bigram_lexical_baseline"
_ID = re.compile(r"[a-zA-Z0-9_.-]{1,100}\Z")


def _valid_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} must be a non-empty synthetic identifier")
    return value


def _valid_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    ids = [_valid_id(item, field) for item in value]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{field} contains duplicate document IDs")
    return ids


def convert(
    report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Reject unsafe inputs, retaining only query IDs and ranked document IDs."""
    if not isinstance(report, dict) or report.get("dataset_id") != DATASET_ID:
        raise ValueError("Only the explicitly synthetic Thai support dataset is accepted")
    if report.get("mode") != MODE:
        raise ValueError("Only the offline lexical baseline is accepted")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases or report.get("case_count") != len(cases):
        raise ValueError("Case count mismatch or empty evaluation")
    if report.get("permission_safe_cases") != len(cases):
        raise ValueError("Source artifact lacks a passing permission boundary")

    ground_truth: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    negative = 0
    injections = 0
    for case in cases:
        if not isinstance(case, dict) or case.get("permission_safe") is not True:
            raise ValueError("Every evaluation case must demonstrate permission filtering")
        query_id = _valid_id(case.get("case_id"), "case_id")
        if query_id in seen:
            raise ValueError(f"Duplicate case_id: {query_id}")
        seen.add(query_id)
        expected = _valid_ids(case.get("expected_ids"), "expected_ids")
        retrieved = _valid_ids(case.get("retrieved_ids"), "retrieved_ids")
        if not isinstance(case.get("expected_abstain"), bool):
            raise ValueError("expected_abstain must be boolean")
        if case["expected_abstain"]:
            negative += 1
            if expected:
                raise ValueError("Abstention cannot have expected relevant IDs")
        if not isinstance(case.get("injection"), bool):
            raise ValueError("injection must be boolean")
        injections += int(case["injection"])
        ground_truth.append({"query_id": query_id, "relevant_document_ids": expected})
        predictions.append({"query_id": query_id, "retrieved_document_ids": retrieved})

    metadata = {
        "dataset_name": DATASET_ID,
        "mode": MODE,
        "data_kind": "SYNTHETIC_FIXTURE",
        "claim_scope": "INTEGRATION_ONLY",
        "case_count": len(cases),
        "abstention_cases": negative,
        "injection_cases": injections,
        "permission_safe_cases": len(cases),
        "limitations": [
            "These are synthetic, lexical baseline results, not Thai semantic-retrieval accuracy.",
            (
                "EvalOps retrieval metrics alone do not verify authorization, "
                "abstention, or injection resistance."
            ),
            (
                "The source's fixture permission-safe checks are separate from "
                "its retrieval-quality metrics."
            ),
        ],
    }
    return ground_truth, predictions, metadata


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Local synthetic report JSON")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    ground_truth, predictions, metadata = convert(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "ground_truth.jsonl", ground_truth)
    _write_jsonl(args.output_dir / "predictions.jsonl", predictions)
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {metadata['case_count']} synthetic cases to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
