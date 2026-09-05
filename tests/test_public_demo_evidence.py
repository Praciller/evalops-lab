from __future__ import annotations

from pathlib import Path

from scripts.generate_public_demo_evidence import generate


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
        == [
            Path("artifacts/demo-miracl-th-mini-v1.json"),
            Path("artifacts/demo-retrieval-fixture-v1.json"),
            Path("index.json"),
        ]
    )
    assert [path.read_bytes() for path in (first / file for file in first_files)] == [
        path.read_bytes() for path in (second / file for file in second_files)
    ]
