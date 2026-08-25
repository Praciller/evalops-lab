from __future__ import annotations

import json
from pathlib import Path

from evalops.datasets.ragtruth_prepare import RAGTRUTH_REVISION, prepare_ragtruth

FIXTURE = Path("datasets/fixtures/ragtruth-mini")


def test_mini_preparation_is_offline_and_reports_fixture_statistics() -> None:
    summary = prepare_ragtruth(output_dir=Path("unused"), mini=True, fixture_dir=FIXTURE)

    assert summary.mode == "mini"
    assert summary.source_revision == "synthetic-fixture-v1"
    assert summary.responses == 8
    assert summary.sources == 8
    assert summary.quality_counts == {"good": 6, "incorrect_refusal": 1, "truncated": 1}


def test_local_preparation_is_checksum_aware_and_writes_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "ragtruth"
    response_source = tmp_path / "response.jsonl"
    source_source = tmp_path / "source_info.jsonl"
    response_source.write_text(
        (FIXTURE / "response.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    source_source.write_text(
        (FIXTURE / "source_info.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    summary = prepare_ragtruth(
        output_dir=output_dir,
        response_source=str(response_source),
        source_info_source=str(source_source),
    )
    manifest = json.loads((output_dir / "preparation-manifest.json").read_text(encoding="utf-8"))

    assert summary.source_revision == RAGTRUTH_REVISION
    assert manifest["checksums"] == summary.checksums
    assert (output_dir / "response.jsonl").is_file()
    assert (output_dir / "source_info.jsonl").is_file()
