from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalops.models.hallucination import HallucinationLabel
from evalops.pilot.models import PilotExampleMetadata, PilotManifest
from scripts.run_phase5a_pilot import (
    FRESH_REQUEST_BUDGET,
    OFFICIAL_PROVIDER_NAMES,
    _assert_no_prompt_leakage,
    _partition_resume_ids,
    _validate_pilot_manifest,
    _validate_preflight,
    estimate_request_count,
    preflight_request_count,
)


def test_official_provider_scope_excludes_non_reproducible_or_blocked_paths() -> None:
    assert OFFICIAL_PROVIDER_NAMES == ("gemini",)


def test_request_estimate_respects_the_300_request_ceiling() -> None:
    assert estimate_request_count(120, include_consistency=False) == 122
    assert estimate_request_count(120, include_consistency=True) == 146
    assert estimate_request_count(121, include_consistency=True) == 147


def test_resume_task_uses_a_fresh_150_request_budget() -> None:
    assert FRESH_REQUEST_BUDGET == 150


def test_preflight_request_count_preserves_real_requests_across_restarts() -> None:
    assert preflight_request_count(0) == 2
    assert preflight_request_count(2) == 4


def test_frozen_manifest_requires_the_exact_six_balanced_strata() -> None:
    records = [
        PilotExampleMetadata(
            example_id=f"{index}",
            source_id=f"source-{index}",
            task_type=task_type,
            human_label=label,
            stratum=f"{task_type}:{label.value}",
        )
        for index, (task_type, label) in enumerate(
            (task_type, label)
            for task_type in ("Data2txt", "QA", "Summary")
            for label in HallucinationLabel
            for _ in range(20)
        )
    ]
    manifest = PilotManifest(
        pilot_id="ragtruth-llm-judge-pilot-v1",
        manifest_version="ragtruth-llm-judge-manifest-v1",
        dataset_revision="fixture",
        split="test",
        quality_filter=["good"],
        sampling_seed=20260825,
        sampling_strategy="fixture",
        records=records,
    )

    _validate_pilot_manifest(manifest)


def test_prompt_leakage_guard_accepts_only_context_response_pairs() -> None:
    _assert_no_prompt_leakage({"example": ("context", "response")})

    with pytest.raises(ValueError, match="context/response pairs"):
        _assert_no_prompt_leakage({"example": {"context": "context", "label": "GROUNDED"}})


def test_preflight_gate_accepts_a_generic_single_provider(tmp_path: Path) -> None:
    artifact = tmp_path / "preflight.json"
    artifact.write_text(
        json.dumps(
            {
                "external_requests": 4,
                "repair_external_requests": 4,
                "selected_providers": ["fake-provider"],
                "readiness": {
                    "llm_judge_ready": True,
                    "qualified_providers": ["fake-provider"],
                },
                "providers": {
                    "fake-provider": {
                        "api_success_count": 2,
                        "parse_success_count": 2,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert _validate_preflight(artifact)["selected_providers"] == ["fake-provider"]


def test_resume_partition_keeps_failed_and_never_attempted_ids_pending() -> None:
    partition = _partition_resume_ids(
        ["a", "b", "c", "d"],
        successful_primary_ids={"a"},
        attempted_ids={"a", "b"},
    )

    assert partition == {
        "successful_primary_ids": ["a"],
        "previous_failed_ids": ["b"],
        "never_attempted_ids": ["c", "d"],
        "pending_ids": ["b", "c", "d"],
    }
