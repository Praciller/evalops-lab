from __future__ import annotations

import json
from pathlib import Path

from evalops.cli import main


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_retrieval_cli_writes_a_traceable_result(tmp_path: Path, capsys: object) -> None:
    ground_truth = tmp_path / "ground-truth.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    output = tmp_path / "result.json"
    _write_jsonl(ground_truth, [{"query_id": "q1", "relevant_document_ids": ["d1"]}])
    _write_jsonl(predictions, [{"query_id": "q1", "retrieved_document_ids": ["d1"]}])

    exit_code = main(
        [
            "retrieval",
            "evaluate",
            "--ground-truth",
            str(ground_truth),
            "--predictions",
            str(predictions),
            "--k",
            "1",
            "--run-id",
            "run-cli-test",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run"]["run_id"] == "run-cli-test"
    assert payload["metrics"]["recall_at_1"] == 1.0
    assert "run-cli-test" in capsys.readouterr().out


def test_dataset_validate_cli_returns_nonzero_for_invalid_fixture(
    tmp_path: Path, capsys: object
) -> None:
    cases = tmp_path / "cases.jsonl"
    _write_jsonl(cases, [{"id": "bad", "question": "q", "category": "invalid"}])

    exit_code = main(["dataset", "validate", str(cases)])

    assert exit_code == 1
    assert '"valid": false' in capsys.readouterr().out


def test_miracl_mini_prepare_and_benchmark_cli_create_artifact(
    tmp_path: Path, capsys: object
) -> None:
    preparation_code = main(
        [
            "dataset",
            "prepare",
            "miracl",
            "--language",
            "th",
            "--split",
            "dev",
            "--mini",
        ]
    )
    preparation_payload = json.loads(capsys.readouterr().out)

    output = tmp_path / "miracl-mini.json"
    benchmark_code = main(
        [
            "benchmark",
            "miracl",
            "--mini",
            "--k",
            "5",
            "--run-id",
            "cli-mini",
            "--output",
            str(output),
        ]
    )
    benchmark_payload = json.loads(capsys.readouterr().out)

    assert preparation_code == benchmark_code == 0
    assert preparation_payload["mode"] == "mini"
    assert benchmark_payload["run"]["run_id"] == "cli-mini"
    assert output.exists()


def test_ragtruth_mini_prepare_and_evaluate_cli_create_artifact(
    tmp_path: Path, capsys: object
) -> None:
    preparation_code = main(["dataset", "prepare", "ragtruth", "--mini"])
    preparation_payload = json.loads(capsys.readouterr().out)

    output = tmp_path / "ragtruth-mini.json"
    evaluation_code = main(
        [
            "hallucination",
            "evaluate",
            "--dataset",
            "ragtruth",
            "--mini",
            "--split",
            "test",
            "--evaluator",
            "heuristic-baseline",
            "--output",
            str(output),
        ]
    )
    evaluation_payload = json.loads(capsys.readouterr().out)

    assert preparation_code == evaluation_code == 0
    assert preparation_payload["mode"] == "mini"
    assert evaluation_payload["run"]["run_id"] == "local-ragtruth-run"
    assert evaluation_payload["details"]["counts"] == {"total": 8, "included": 6, "excluded": 2}
    assert output.exists()


def test_regression_compare_cli_uses_explicit_policy(tmp_path: Path, capsys: object) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy = tmp_path / "policy.json"
    baseline.write_text(json.dumps({"run": {"run_id": "base"}, "metrics": {"recall_at_5": 0.8}}))
    candidate.write_text(
        json.dumps({"run": {"run_id": "candidate"}, "metrics": {"recall_at_5": 0.79}})
    )
    policy.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "metric_name": "recall_at_5",
                        "direction": "higher_is_better",
                        "max_degradation": 0.02,
                    }
                ]
            }
        )
    )

    exit_code = main(
        [
            "regression",
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--policy",
            str(policy),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["passed"] is True
