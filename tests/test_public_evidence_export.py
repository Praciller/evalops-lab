import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evalops.export import (
    ClaimScope,
    DataKind,
    PopulationCompatibility,
    VerificationStatus,
    adapt_evaluation_result,
    adapt_regression_report,
    build_public_index,
    serialize_public_artifact,
)
from evalops.export.compatibility import assess_population_compatibility


def _run_payload() -> dict[str, object]:
    return {
        "evaluation_type": "retrieval",
        "run": {
            "run_id": "fixture-run-v1",
            "dataset_name": "thai-rag-fixture",
            "dataset_version": "synthetic-fixture-v1",
            "system_name": "fixture-system",
            "top_k": 5,
            "evaluator_versions": {"retrieval": "deterministic-v1"},
            "timestamp": datetime(2026, 9, 5, 7, 0, tzinfo=UTC).isoformat(),
            "git_commit": "f" * 40,
            "benchmark": None,
            "language": "th",
            "split": "test",
            "retriever": "bm25",
            "retriever_version": "bm25-local-v1",
        },
        "metrics": {"recall_at_5": 0.5, "hit_rate_at_5": 0.75},
        "failures": [
            {
                "category": "RETRIEVAL_MISS",
                "failure_class": "system_failure",
                "message": "internal detail must not be published",
                "evidence": {"relevant_document_ids": ["doc-2"]},
            }
        ],
        "details": {
            "per_query": {
                "q-2": {
                    "metrics": {"recall_at_5": 0.0},
                    "failure_category": "RETRIEVAL_MISS",
                    "retrieved_document_ids": ["doc-9"],
                    "relevant_document_ids": ["doc-2"],
                    "scores": [0.1],
                },
                "q-1": {
                    "metrics": {"recall_at_5": 1.0},
                    "failure_category": "PASS",
                    "retrieved_document_ids": ["doc-1"],
                    "relevant_document_ids": ["doc-1"],
                    "scores": [1.0],
                },
            },
            "raw_response": "must not be published",
            "api_key": "must not be published",
            "authorization": "Bearer must-not-be-published",
            "local_path": r"C:\private\corpus.jsonl",
            "hidden_reasoning": "must not be published",
            "raw_corpus": "must not be published",
        },
    }


def _artifact(
    payload: dict[str, object] | None = None,
    *,
    artifact_id: str = "run-fixture-v1",
    run_id: str | None = None,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    data_kind: DataKind = DataKind.SYNTHETIC_FIXTURE,
    claim_scope: ClaimScope = ClaimScope.INTEGRATION_ONLY,
):
    source = payload or _run_payload()
    if run_id is not None:
        source = source | {"run": source["run"] | {"run_id": run_id}}
    return adapt_evaluation_result(
        source,
        artifact_id=artifact_id,
        verification_status=verification_status,
        data_kind=data_kind,
        claim_scope=claim_scope,
        limitations=["Synthetic fixture; not an official benchmark result."],
    )


def _comparison_artifact(
    *,
    artifact_id: str = "comparison-v1",
    baseline_artifact_id: str = "baseline-artifact-v1",
    candidate_artifact_id: str = "candidate-artifact-v1",
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    data_kind: DataKind = DataKind.SYNTHETIC_FIXTURE,
    claim_scope: ClaimScope = ClaimScope.INTEGRATION_ONLY,
    population_compatibility: PopulationCompatibility = PopulationCompatibility.UNVERIFIED,
):
    return adapt_regression_report(
        {
            "baseline_run_id": "baseline-v1",
            "candidate_run_id": "candidate-v1",
            "passed": True,
            "comparisons": [
                {
                    "metric_name": "recall_at_5",
                    "direction": "higher_is_better",
                    "baseline": 0.5,
                    "current": 0.6,
                    "delta": 0.1,
                    "status": "PASS",
                    "reason": "within configured regression allowance",
                }
            ],
        },
        artifact_id=artifact_id,
        baseline_artifact_id=baseline_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        verification_status=verification_status,
        data_kind=data_kind,
        claim_scope=claim_scope,
        population_compatibility=population_compatibility,
    )


def test_run_adapter_publishes_allowlisted_evidence_only() -> None:
    artifact = _artifact()

    assert artifact.schema_version == "public-evidence-v1"
    assert artifact.artifact_type == "run"
    assert [record.record_ref for record in artifact.evidence] == ["q-1", "q-2"]
    assert [failure.record_ref for failure in artifact.failures] == ["q-2"]
    serialized = serialize_public_artifact(artifact)
    assert "raw_response" not in serialized
    assert "api_key" not in serialized
    assert "internal detail" not in serialized
    assert "authorization" not in serialized
    assert "private\\corpus" not in serialized
    assert "hidden_reasoning" not in serialized
    assert "raw_corpus" not in serialized


def test_serialization_is_deterministic_and_stable() -> None:
    artifact = _artifact()

    first = serialize_public_artifact(artifact)
    second = serialize_public_artifact(artifact)

    assert first == second
    assert first.endswith("\n")
    assert list(json.loads(first)["metrics"]) == ["hit_rate_at_5", "recall_at_5"]


def test_external_record_identity_is_not_published_by_default() -> None:
    artifact = adapt_evaluation_result(
        _run_payload(),
        artifact_id="official-run-v1",
        verification_status=VerificationStatus.UNVERIFIED,
        data_kind=DataKind.OFFICIAL_BENCHMARK,
        claim_scope=ClaimScope.BENCHMARK_RESULT,
    )

    assert artifact.evidence == []
    assert [failure.record_ref for failure in artifact.failures] == ["run:fixture-run-v1"]


@pytest.mark.parametrize(
    ("data_kind", "claim_scope"),
    [
        (DataKind.SYNTHETIC_FIXTURE, ClaimScope.BENCHMARK_RESULT),
        (DataKind.SYNTHETIC_FIXTURE, ClaimScope.PROTOCOL_SPECIFIC),
        (DataKind.CURATED_DATASET, ClaimScope.BENCHMARK_RESULT),
    ],
)
def test_rejects_incompatible_claim_dimensions(
    data_kind: DataKind, claim_scope: ClaimScope
) -> None:
    with pytest.raises(ValueError, match="incompatible claim dimensions"):
        _artifact(data_kind=data_kind, claim_scope=claim_scope)


def test_official_benchmark_claim_is_accepted() -> None:
    artifact = _artifact(
        artifact_id="official-run-v1",
        verification_status=VerificationStatus.UNVERIFIED,
        data_kind=DataKind.OFFICIAL_BENCHMARK,
        claim_scope=ClaimScope.BENCHMARK_RESULT,
    )

    assert artifact.claim_scope is ClaimScope.BENCHMARK_RESULT


def test_completed_run_and_comparison_reject_not_run() -> None:
    with pytest.raises(ValueError, match="NOT_RUN"):
        _artifact(verification_status=VerificationStatus.NOT_RUN)
    with pytest.raises(ValueError, match="NOT_RUN"):
        _comparison_artifact(verification_status=VerificationStatus.NOT_RUN)


def test_invalid_source_and_unsafe_public_text_fail_closed() -> None:
    with pytest.raises((ValidationError, ValueError)):
        adapt_evaluation_result(
            {"evaluation_type": "retrieval"},
            artifact_id="broken",
            verification_status=VerificationStatus.VERIFIED,
            data_kind=DataKind.SYNTHETIC_FIXTURE,
            claim_scope=ClaimScope.INTEGRATION_ONLY,
        )

    with pytest.raises(ValueError, match="unsafe"):
        _artifact().__class__.model_validate(
            _artifact().model_dump(mode="json") | {"limitations": ["api_key=secret"]}
        )


def test_index_uses_only_explicit_artifacts_and_sorts_them() -> None:
    first = _artifact()
    second = adapt_evaluation_result(
        _run_payload() | {"run": _run_payload()["run"] | {"run_id": "another-run-v1"}},
        artifact_id="another-run-v1",
        verification_status=VerificationStatus.VERIFIED,
        data_kind=DataKind.SYNTHETIC_FIXTURE,
        claim_scope=ClaimScope.INTEGRATION_ONLY,
    )

    index = build_public_index([first, second])

    assert index.schema_version == "public-evidence-v1"
    assert [item.artifact_id for item in index.artifacts] == [
        "another-run-v1",
        "run-fixture-v1",
    ]
    assert not hasattr(index, "data_kind")
    assert not hasattr(index, "claim_scope")
    assert index.catalog_status == "EXPLICIT_ALLOWLIST"
    first_serialization = serialize_public_artifact(index)
    assert first_serialization == serialize_public_artifact(index)
    assert '"catalog_status": "EXPLICIT_ALLOWLIST"' in first_serialization


def test_index_rejects_duplicate_artifact_ids() -> None:
    artifact = _artifact()

    with pytest.raises(ValueError, match="duplicate artifact_id"):
        build_public_index([artifact, artifact])


@pytest.mark.parametrize(
    ("baseline_artifact_id", "candidate_artifact_id"),
    [
        ("missing-baseline", "candidate-run-v1"),
        ("baseline-run-v1", "missing-candidate"),
    ],
)
def test_index_rejects_dangling_comparison_references(
    baseline_artifact_id: str, candidate_artifact_id: str
) -> None:
    comparison = _comparison_artifact(
        baseline_artifact_id=baseline_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
    )

    with pytest.raises(ValueError, match="must reference a run artifact in the same index"):
        build_public_index([comparison])


def test_index_rejects_comparison_referencing_non_run_artifact() -> None:
    baseline_comparison = _comparison_artifact(artifact_id="baseline-comparison-v1")
    comparison = _comparison_artifact(
        artifact_id="comparison-v2",
        baseline_artifact_id="baseline-comparison-v1",
        candidate_artifact_id="candidate-run-v1",
    )
    candidate = _artifact(artifact_id="candidate-run-v1")

    with pytest.raises(ValueError, match="must reference a run artifact in the same index"):
        build_public_index([baseline_comparison, comparison, candidate])


def test_comparison_rejects_self_comparison() -> None:
    with pytest.raises(ValueError, match="cannot compare an artifact with itself"):
        _comparison_artifact(
            baseline_artifact_id="same-artifact-v1",
            candidate_artifact_id="same-artifact-v1",
        )


def test_mixed_index_preserves_child_claim_dimensions_without_catalog_claims() -> None:
    synthetic = _artifact(artifact_id="synthetic-run-v1", run_id="baseline-v1")
    official = _artifact(
        artifact_id="official-run-v1",
        run_id="candidate-v1",
        verification_status=VerificationStatus.UNVERIFIED,
        data_kind=DataKind.OFFICIAL_BENCHMARK,
        claim_scope=ClaimScope.BENCHMARK_RESULT,
    )
    comparison = _comparison_artifact(
        artifact_id="comparison-v1",
        baseline_artifact_id="synthetic-run-v1",
        candidate_artifact_id="official-run-v1",
        data_kind=DataKind.CURATED_DATASET,
        claim_scope=ClaimScope.PROTOCOL_SPECIFIC,
    )

    with pytest.raises(ValueError, match="data_kind"):
        build_public_index([comparison, official, synthetic])


def test_population_compatibility_is_typed_and_same_population_matches() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1", run_id="baseline-v1")
    candidate = _artifact(artifact_id="candidate-run-v1")

    assert (
        assess_population_compatibility(baseline, candidate)
        is PopulationCompatibility.MATCHED
    )


def test_population_mismatch_is_incompatible() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1", run_id="baseline-v1")
    candidate = _artifact(
        _run_payload()
        | {"run": _run_payload()["run"] | {"dataset_version": "synthetic-v2"}},
        artifact_id="candidate-run-v1",
    )

    assert (
        assess_population_compatibility(baseline, candidate)
        is PopulationCompatibility.INCOMPATIBLE
    )


def test_index_rejects_matched_comparison_when_population_differs() -> None:
    baseline = _artifact(artifact_id="baseline-run-v1", run_id="baseline-v1")
    candidate = _artifact(
        _run_payload() | {"run": _run_payload()["run"] | {"top_k": 10}},
        artifact_id="candidate-run-v1",
        run_id="candidate-v1",
    )
    comparison = _comparison_artifact(
        baseline_artifact_id=baseline.artifact_id,
        candidate_artifact_id=candidate.artifact_id,
        population_compatibility=PopulationCompatibility.MATCHED,
    )

    with pytest.raises(ValueError, match="population compatibility"):
        build_public_index([baseline, candidate, comparison])


def test_index_rejects_comparison_claim_stronger_than_operand() -> None:
    baseline = _artifact(
        artifact_id="baseline-run-v1",
        run_id="baseline-v1",
        verification_status=VerificationStatus.PARTIAL,
    )
    candidate = _artifact(artifact_id="candidate-run-v1", run_id="candidate-v1")
    comparison = _comparison_artifact(
        baseline_artifact_id=baseline.artifact_id,
        candidate_artifact_id=candidate.artifact_id,
        verification_status=VerificationStatus.VERIFIED,
    )

    with pytest.raises(ValueError, match="verification"):
        build_public_index([baseline, candidate, comparison])


def test_regression_adapter_preserves_standard_comparison_fields() -> None:
    artifact = adapt_regression_report(
        {
            "baseline_run_id": "baseline-v1",
            "candidate_run_id": "candidate-v1",
            "passed": True,
            "comparisons": [
                {
                    "metric_name": "recall_at_5",
                    "direction": "higher_is_better",
                    "baseline": 0.5,
                    "current": 0.6,
                    "delta": 0.1,
                    "status": "PASS",
                    "reason": "within configured regression allowance",
                }
            ],
        },
        artifact_id="comparison-v1",
        baseline_artifact_id="baseline-artifact-v1",
        candidate_artifact_id="candidate-artifact-v1",
        verification_status=VerificationStatus.VERIFIED,
        data_kind=DataKind.SYNTHETIC_FIXTURE,
        claim_scope=ClaimScope.INTEGRATION_ONLY,
    )

    comparison = artifact.comparisons[0]
    assert artifact.baseline_run_id == "baseline-v1"
    assert comparison.candidate_value == 0.6
    assert comparison.delta == 0.1
    assert comparison.status == "PASS"
