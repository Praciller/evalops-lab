import json
from datetime import UTC, datetime

from evalops.cli import main


def test_evidence_cli_exports_then_indexes_explicit_artifact(tmp_path, capsys) -> None:
    source_path = tmp_path / "result.json"
    artifact_path = tmp_path / "public-run.json"
    index_path = tmp_path / "index.json"
    source_path.write_text(
        json.dumps(
            {
                "evaluation_type": "retrieval",
                "run": {
                    "run_id": "cli-run-v1",
                    "dataset_name": "synthetic-cli",
                    "dataset_version": "fixture-v1",
                    "system_name": "cli-system",
                    "top_k": 5,
                    "timestamp": datetime(2026, 9, 5, tzinfo=UTC).isoformat(),
                },
                "metrics": {"recall_at_5": 1.0},
                "details": {"raw_response": "excluded"},
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "evidence",
                "export",
                "--source",
                str(source_path),
                "--source-type",
                "run",
                "--output",
                str(artifact_path),
                "--artifact-id",
                "cli-artifact-v1",
                "--verification-status",
                "VERIFIED",
                "--data-kind",
                "SYNTHETIC_FIXTURE",
                "--claim-scope",
                "INTEGRATION_ONLY",
            ]
        )
        == 0
    )
    capsys.readouterr()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["artifact_type"] == "run"
    assert "raw_response" not in artifact

    assert (
        main(
            [
                "evidence",
                "index",
                "--artifact",
                str(artifact_path),
                "--output",
                str(index_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert [item["artifact_id"] for item in index["artifacts"]] == ["cli-artifact-v1"]


def test_evidence_cli_rejects_comparison_without_explicit_artifact_refs(tmp_path, capsys) -> None:
    source_path = tmp_path / "comparison.json"
    output_path = tmp_path / "comparison-public.json"
    source_path.write_text(json.dumps({"passed": True, "comparisons": []}), encoding="utf-8")

    assert (
        main(
            [
                "evidence",
                "export",
                "--source",
                str(source_path),
                "--source-type",
                "comparison",
                "--output",
                str(output_path),
                "--artifact-id",
                "comparison-v1",
                "--verification-status",
                "VERIFIED",
                "--data-kind",
                "SYNTHETIC_FIXTURE",
                "--claim-scope",
                "INTEGRATION_ONLY",
            ]
        )
        == 2
    )
    assert not output_path.exists()
    assert "comparison exports require" in capsys.readouterr().err
