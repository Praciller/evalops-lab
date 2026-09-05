import json
from datetime import UTC, datetime

import pytest

from evalops.cli import main
from evalops.export import (
    ClaimScope,
    DataKind,
    VerificationStatus,
    adapt_regression_report,
    serialize_public_artifact,
)


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


def test_evidence_cli_types_population_compatibility(tmp_path, capsys) -> None:
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
                "--baseline-artifact-id",
                "baseline-v1",
                "--candidate-artifact-id",
                "candidate-v1",
                "--population-compatibility",
                "UNVERIFIED",
            ]
        )
        == 0
    )
    capsys.readouterr()
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["population_compatibility"] == "UNVERIFIED"


def test_evidence_cli_rejects_unknown_population_compatibility(tmp_path) -> None:
    source_path = tmp_path / "comparison.json"
    output_path = tmp_path / "comparison-public.json"
    source_path.write_text(json.dumps({"passed": True, "comparisons": []}), encoding="utf-8")

    with pytest.raises(SystemExit):
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
                "--baseline-artifact-id",
                "baseline-v1",
                "--candidate-artifact-id",
                "candidate-v1",
                "--population-compatibility",
                "NOT_A_COMPATIBILITY",
            ]
        )


def test_evidence_cli_rejects_invalid_claim_combination_without_writing(tmp_path, capsys) -> None:
    source_path = tmp_path / "result.json"
    output_path = tmp_path / "invalid-public.json"
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
                str(output_path),
                "--artifact-id",
                "cli-artifact-v1",
                "--verification-status",
                "VERIFIED",
                "--data-kind",
                "SYNTHETIC_FIXTURE",
                "--claim-scope",
                "BENCHMARK_RESULT",
            ]
        )
        == 2
    )
    assert not output_path.exists()
    assert "incompatible claim dimensions" in capsys.readouterr().err


def test_evidence_cli_rejects_duplicate_index_identity(tmp_path, capsys) -> None:
    artifact_path = tmp_path / "artifact.json"
    index_path = tmp_path / "duplicate-index.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "public-evidence-v1",
                "artifact_type": "run",
                "artifact_id": "run-v1",
                "verification_status": "VERIFIED",
                "data_kind": "SYNTHETIC_FIXTURE",
                "claim_scope": "INTEGRATION_ONLY",
                "limitations": [],
                "run": {
                    "evaluation_type": "retrieval",
                    "run_id": "run-v1",
                    "dataset_name": "synthetic-cli",
                    "dataset_version": "fixture-v1",
                    "system_name": "cli-system",
                    "top_k": 5,
                    "timestamp": datetime(2026, 9, 5, tzinfo=UTC).isoformat(),
                    "evaluator_versions": {},
                },
                "metrics": {},
                "failures": [],
                "evidence": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "evidence",
                "index",
                "--artifact",
                str(artifact_path),
                "--artifact",
                str(artifact_path),
                "--output",
                str(index_path),
            ]
        )
        == 2
    )
    assert not index_path.exists()
    assert "duplicate artifact_id" in capsys.readouterr().err


def test_evidence_cli_rejects_dangling_comparison_reference(tmp_path, capsys) -> None:
    comparison_path = tmp_path / "comparison.json"
    index_path = tmp_path / "dangling-index.json"
    comparison = adapt_regression_report(
        {"passed": True, "comparisons": []},
        artifact_id="comparison-v1",
        baseline_artifact_id="missing-baseline",
        candidate_artifact_id="missing-candidate",
        verification_status=VerificationStatus.VERIFIED,
        data_kind=DataKind.CURATED_DATASET,
        claim_scope=ClaimScope.PROTOCOL_SPECIFIC,
    )
    comparison_path.write_text(serialize_public_artifact(comparison), encoding="utf-8")

    assert (
        main(
            [
                "evidence",
                "index",
                "--artifact",
                str(comparison_path),
                "--output",
                str(index_path),
            ]
        )
        == 2
    )
    assert not index_path.exists()
    assert "must reference a run artifact in the same index" in capsys.readouterr().err
