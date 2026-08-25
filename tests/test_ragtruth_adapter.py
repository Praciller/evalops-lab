from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.models.hallucination import AnnotationPolicy, HallucinationLabel

FIXTURE = Path("datasets/fixtures/ragtruth-mini")


def test_mini_fixture_normalizes_sources_responses_and_annotation_subtleties() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")

    assert len(dataset.examples) == 8
    assert {example.task_type for example in dataset.examples} == {"QA", "Summary", "Data2txt"}
    assert dataset.examples[0].source_context
    assert dataset.examples[0].raw_response["response"] == dataset.examples[0].response
    assert dataset.examples[1].spans[0].text == "Paris"
    assert dataset.examples[1].spans[0].offset_valid is True
    assert dataset.examples[3].spans[0].implicit_true is True
    assert dataset.examples[4].spans[0].due_to_null is True
    assert dataset.examples[5].quality == "incorrect_refusal"
    assert dataset.examples[6].quality == "truncated"
    assert dataset.examples[7].span_validation_issues


def test_annotation_policy_keeps_strict_groundedness_distinct_from_factual_correctness() -> None:
    dataset = load_ragtruth_dataset(FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl")
    implicit_true = dataset.examples[3]

    assert (
        implicit_true.human_label(AnnotationPolicy.STRICT_GROUNDEDNESS)
        == HallucinationLabel.HALLUCINATED
    )
    assert (
        implicit_true.human_label(AnnotationPolicy.FACTUAL_CORRECTNESS)
        == HallucinationLabel.GROUNDED
    )


def test_split_filter_and_quality_values_are_preserved() -> None:
    dataset = load_ragtruth_dataset(
        FIXTURE / "response.jsonl", FIXTURE / "source_info.jsonl", split="test"
    )

    assert len(dataset.examples) == 8
    assert {example.split for example in dataset.examples} == {"test"}
    assert dataset.quality_counts == {
        "good": 6,
        "incorrect_refusal": 1,
        "truncated": 1,
    }


def test_adapter_rejects_duplicate_response_ids(tmp_path: Path) -> None:
    response_path = tmp_path / "response.jsonl"
    source_path = tmp_path / "source_info.jsonl"
    source_path.write_text(
        json.dumps(
            {
                "source_id": "s1",
                "task_type": "QA",
                "source": "fixture",
                "source_info": "evidence",
                "prompt": "question",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = {
        "id": "r1",
        "source_id": "s1",
        "model": "fixture-model",
        "temperature": 0.0,
        "labels": [],
        "split": "test",
        "quality": "good",
        "response": "evidence",
    }
    response_path.write_text(
        json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate response ID"):
        load_ragtruth_dataset(response_path, source_path)


def test_offset_anomaly_is_reported_without_rewriting_the_span(tmp_path: Path) -> None:
    response_path = tmp_path / "response.jsonl"
    source_path = tmp_path / "source_info.jsonl"
    source_path.write_text(
        json.dumps(
            {
                "source_id": "s1",
                "task_type": "Summary",
                "source": "fixture",
                "source_info": "evidence",
                "prompt": "summarize",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    response_path.write_text(
        json.dumps(
            {
                "id": "r1",
                "source_id": "s1",
                "model": "fixture-model",
                "temperature": 0.0,
                "labels": [
                    {
                        "start": 0,
                        "end": 4,
                        "text": "wrong",
                        "label_type": "Evident Baseless Info",
                    }
                ],
                "split": "test",
                "quality": "good",
                "response": "right",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    dataset = load_ragtruth_dataset(response_path, source_path)

    assert dataset.examples[0].spans[0].text == "wrong"
    assert dataset.examples[0].spans[0].offset_valid is False
    assert any(issue.code == "TEXT_OFFSET_MISMATCH" for issue in dataset.validation_issues)
