"""Guided CSV normalization: deterministic canonical bytes and private source provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evalops.datasets.io import load_retrieval_ground_truth, load_retrieval_predictions
from evalops.workspace.ingestion.csv_adapter import (
    normalize_retrieval_csv,
    normalize_retrieval_csv_bytes,
)
from evalops.workspace.ingestion.models import CsvMapping, InputKind, InputValidationError
from evalops.workspace.ingestion.service import register_imported_csv
from evalops.workspace.storage import WorkspaceStore

GT_KIND = InputKind.RETRIEVAL_GROUND_TRUTH
PRED_KIND = InputKind.RETRIEVAL_PREDICTIONS
MAPPING = CsvMapping(query_id_column="qid", document_ids_column="docs", document_ids_delimiter="|")
GT_CSV = b"qid,docs\nq1,d1|d2\nq2,\n"


def test_normalized_csv_is_deterministic_and_uses_existing_gt_loader(tmp_path: Path) -> None:
    canonical, summary = normalize_retrieval_csv_bytes(GT_CSV, kind=GT_KIND, mapping=MAPPING)
    reference, _ = normalize_retrieval_csv_bytes(
        b"qid,docs\r\n q1 , d1 | d2 \r\nq2,\r\n", kind=GT_KIND, mapping=MAPPING
    )
    assert canonical == reference
    assert canonical.endswith(b"\n")
    assert summary.record_count == 2
    assert summary.content_sha256 == hashlib.sha256(canonical).hexdigest()
    output = tmp_path / "canonical.jsonl"
    output.write_bytes(canonical)
    assert load_retrieval_ground_truth(output) == {"q1": ["d1", "d2"], "q2": []}
    assert [json.loads(line) for line in canonical.decode().splitlines()] == [
        {"query_id": "q1", "relevant_document_ids": ["d1", "d2"]},
        {"query_id": "q2", "relevant_document_ids": []},
    ]


def test_predictions_custom_headers_and_empty_document_lists(tmp_path: Path) -> None:
    mapping = CsvMapping(query_id_column="Question Key", document_ids_column="Retrieved")
    source = tmp_path / "scores.csv"
    source.write_text('Question Key,Retrieved\nquestion-1,"d3|d2"\nquestion-2,\n', encoding="utf-8")
    canonical, summary = normalize_retrieval_csv(source, kind=PRED_KIND, mapping=mapping)
    dest = tmp_path / "normalized.jsonl"
    dest.write_bytes(canonical)
    assert summary.unique_query_count == 2
    assert load_retrieval_predictions(dest) == {"question-1": ["d3", "d2"], "question-2": []}


def test_imported_csv_persists_only_canonical_jsonl_and_both_hashes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = WorkspaceStore(root)
    store.initialize()
    workspace_id = store.create_workspace("CSV").workspace_id
    result = register_imported_csv(
        store, workspace_id, kind=GT_KIND, data=GT_CSV, source_filename="input.csv", mapping=MAPPING
    )
    manifest = result.manifest
    assert manifest.source_filename == "input.csv"
    assert manifest.source_sha256 == hashlib.sha256(GT_CSV).hexdigest()
    assert manifest.content_sha256 != manifest.source_sha256
    path = root / "workspaces" / workspace_id / manifest.stored_relative_path
    assert path.suffix == ".jsonl"
    assert b"relevant_document_ids" in path.read_bytes()
    assert store.get_input(workspace_id, manifest.input_id) == manifest
    assert list(root.rglob("*.csv")) == []


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (b"", "EMPTY_INPUT"),
        (b"qid,docs\n", "EMPTY_INPUT"),
        (b"\xff\xfe", "INVALID_UTF8"),
        (b"qid,docs\nq1,d1\nq1,d2\n", "DUPLICATE_QUERY_ID"),
        (b'qid,docs\nq1,"unclosed\n', "INVALID_CSV"),
        (b"qid,docs\nq1,d1,extra\n", "INVALID_CSV"),
        (b"qid,qid\nq1,d1\n", "DUPLICATE_HEADERS"),
        (b"qid,docs\n,d1\n", "INVALID_CSV"),
    ],
)
def test_invalid_csv_fails_closed(payload: bytes, error_code: str) -> None:
    with pytest.raises(InputValidationError) as caught:
        normalize_retrieval_csv_bytes(payload, kind=GT_KIND, mapping=MAPPING)
    assert caught.value.code == error_code
    assert "q1,d1" not in str(caught.value)


def test_missing_header_and_equal_mapped_columns_fail_closed() -> None:
    with pytest.raises(InputValidationError) as caught:
        normalize_retrieval_csv_bytes(b"other,docs\nq1,d1\n", kind=GT_KIND, mapping=MAPPING)
    assert caught.value.code == "MISSING_COLUMN"
    equal = CsvMapping(query_id_column="qid", document_ids_column=" qid ")
    with pytest.raises(InputValidationError) as caught:
        normalize_retrieval_csv_bytes(GT_CSV, kind=GT_KIND, mapping=equal)
    assert caught.value.code == "INVALID_MAPPING"


def test_prediction_duplicates_are_rejected_by_existing_pydantic_contract() -> None:
    with pytest.raises(InputValidationError) as caught:
        normalize_retrieval_csv_bytes(b"qid,docs\nq1,d1|d1\n", kind=PRED_KIND, mapping=MAPPING)
    assert caught.value.code == "INVALID_CSV"


def test_delimiter_must_be_one_character() -> None:
    with pytest.raises(ValidationError):
        CsvMapping(query_id_column="qid", document_ids_column="docs", document_ids_delimiter="||")



def test_csv_expansion_beyond_runtime_cap_is_rejected_before_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    store = WorkspaceStore(root)
    store.initialize()
    workspace_id = store.create_workspace("CSV boundary").workspace_id

    # Raw CSV fits, but canonical JSONL is larger due to field names/JSON encoding.
    import evalops.workspace.ingestion.service as ingestion_service

    monkeypatch.setattr(ingestion_service, "MAX_INPUT_BYTES", len(GT_CSV))
    canonical, _ = normalize_retrieval_csv_bytes(GT_CSV, kind=GT_KIND, mapping=MAPPING)
    assert len(GT_CSV) <= ingestion_service.MAX_INPUT_BYTES < len(canonical)

    with pytest.raises(InputValidationError) as caught:
        register_imported_csv(
            store,
            workspace_id,
            kind=GT_KIND,
            data=GT_CSV,
            source_filename="expanded.csv",
            mapping=MAPPING,
        )
    assert caught.value.code == "INPUT_TOO_LARGE"
    assert store.list_inputs(workspace_id) == []
    assert list(root.rglob("*.jsonl")) == []


def test_invalid_csv_never_leaves_canonical_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = WorkspaceStore(root)
    store.initialize()
    workspace_id = store.create_workspace("CSV").workspace_id
    with pytest.raises(InputValidationError):
        register_imported_csv(
            store,
            workspace_id,
            kind=GT_KIND,
            data=b"qid,docs\nq1,d1\nq1,d2\n",
            source_filename="invalid.csv",
            mapping=MAPPING,
        )
    assert store.list_inputs(workspace_id) == []
    assert list(root.rglob("*.jsonl")) == []
