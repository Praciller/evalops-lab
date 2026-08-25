from __future__ import annotations

from pathlib import Path

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.evaluators.hallucination.context import (
    HHEM_CONTEXT_STRATEGY,
    build_hhem_context,
)

FIXTURE = Path("datasets/fixtures/ragtruth-mini")


def test_context_builder_uses_only_task_evidence_and_response() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")
    contexts = {example.example_id: build_hhem_context(example) for example in dataset.examples}

    assert contexts["r1-grounded"].premise == "The capital city is London."
    assert "What is the capital city?" not in contexts["r1-grounded"].premise
    assert contexts["r1-grounded"].hypothesis == "The capital city is London."
    assert contexts["r3-multiple-spans"].task_type == "Summary"
    assert contexts["r4-implicit-true"].premise == '{"field":"The question has a numeric answer."}'
    assert contexts["r4-implicit-true"].strategy == HHEM_CONTEXT_STRATEGY


def test_context_builder_handles_unicode_empty_source_and_is_deterministic() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")
    empty = next(example for example in dataset.examples if example.example_id == "r5-due-to-null")
    first = build_hhem_context(empty)
    second = build_hhem_context(empty)

    assert first.premise == ""
    assert first.model_dump() == second.model_dump()
