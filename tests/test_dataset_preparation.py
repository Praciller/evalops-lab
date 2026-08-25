from __future__ import annotations

from pathlib import Path

import pytest

from scripts.datasets.prepare_utils import prepare_source, sha256_file


def test_snapshot_preparation_is_idempotent_and_refuses_changed_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "upstream.jsonl"
    destination = tmp_path / "external" / "snapshot.jsonl"
    source.write_text("synthetic source\n", encoding="utf-8")

    digest = prepare_source(str(source), destination)
    assert digest == sha256_file(destination)
    assert prepare_source(str(source), destination) == digest

    source.write_text("changed source\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="different checksum"):
        prepare_source(str(source), destination)
