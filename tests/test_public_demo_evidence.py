from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_public_demo_evidence import generate

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILES = [
    Path("artifacts/demo-miracl-th-mini-v1.json"),
    Path("artifacts/demo-retrieval-fixture-v1.json"),
    Path("artifacts/demo-retrieval-reference-v1.json"),
    Path("artifacts/demo-retrieval-regression-v1.json"),
    Path("index.json"),
]


def _json_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*.json"))


def test_public_demo_evidence_generation_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(first)
    generate(second)

    first_files = sorted(path.relative_to(first) for path in first.rglob("*.json"))
    second_files = sorted(path.relative_to(second) for path in second.rglob("*.json"))
    assert (
        first_files
        == second_files
        == EXPECTED_FILES
    )
    assert [path.read_bytes() for path in (first / file for file in first_files)] == [
        path.read_bytes() for path in (second / file for file in second_files)
    ]


def test_checked_in_public_demo_bundle_matches_generator(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generate(generated)
    committed = REPOSITORY_ROOT / "apps" / "web" / "public" / "evidence"

    generated_files = _json_files(generated)
    committed_files = _json_files(committed)
    assert generated_files == committed_files

    for relative_path in generated_files:
        assert (generated / relative_path).read_bytes() == (committed / relative_path).read_bytes()


def test_generated_comparison_uses_expected_policy(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generate(generated)
    comparison = json.loads(
        (generated / "artifacts" / "demo-retrieval-regression-v1.json").read_text(
            encoding="utf-8"
        )
    )
    statuses = {item["metric_name"]: item["status"] for item in comparison["comparisons"]}

    assert comparison["passed"] is False
    assert comparison["population_compatibility"] == "MATCHED"
    assert sum(status == "REGRESSION" for status in statuses.values()) == 4
    assert sum(status == "PASS" for status in statuses.values()) == 1
    assert statuses["precision_at_5"] == "PASS"
