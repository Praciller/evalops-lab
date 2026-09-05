"""Compatibility and claim-safety checks for public comparisons."""

from __future__ import annotations

from evalops.export.models import (
    PopulationCompatibility,
    PublicComparisonArtifactV1,
    PublicRunArtifactV1,
    VerificationStatus,
)

POPULATION_FIELDS = (
    "dataset_name",
    "dataset_version",
    "dataset_revision",
    "evaluation_type",
    "benchmark",
    "language",
    "split",
    "top_k",
    "evaluator_versions",
)

VERIFICATION_STRENGTH = {
    VerificationStatus.UNVERIFIED: 0,
    VerificationStatus.PARTIAL: 1,
    VerificationStatus.VERIFIED: 2,
}


def assess_population_compatibility(
    baseline: PublicRunArtifactV1, candidate: PublicRunArtifactV1
) -> PopulationCompatibility:
    """Recompute same-population compatibility from both run operands."""

    for field in POPULATION_FIELDS:
        if getattr(baseline.run, field) != getattr(candidate.run, field):
            return PopulationCompatibility.INCOMPATIBLE
    return PopulationCompatibility.MATCHED


def validate_comparison_operands(
    comparison: PublicComparisonArtifactV1,
    baseline: PublicRunArtifactV1,
    candidate: PublicRunArtifactV1,
) -> None:
    """Reject public comparisons whose claims contradict their run operands."""

    if comparison.baseline_artifact_id != baseline.artifact_id:
        raise ValueError("comparison baseline artifact reference does not match operand")
    if comparison.candidate_artifact_id != candidate.artifact_id:
        raise ValueError("comparison candidate artifact reference does not match operand")
    if comparison.baseline_run_id is not None and comparison.baseline_run_id != baseline.run.run_id:
        raise ValueError("comparison baseline run reference does not match operand")
    if (
        comparison.candidate_run_id is not None
        and comparison.candidate_run_id != candidate.run.run_id
    ):
        raise ValueError("comparison candidate run reference does not match operand")
    if (
        comparison.data_kind is not baseline.data_kind
        or comparison.data_kind is not candidate.data_kind
    ):
        raise ValueError("comparison data_kind must match both operand runs")
    if (
        comparison.claim_scope is not baseline.claim_scope
        or comparison.claim_scope is not candidate.claim_scope
    ):
        raise ValueError("comparison claim_scope must match both operand runs")

    weakest_operand = min(
        VERIFICATION_STRENGTH[baseline.verification_status],
        VERIFICATION_STRENGTH[candidate.verification_status],
    )
    if VERIFICATION_STRENGTH[comparison.verification_status] > weakest_operand:
        raise ValueError("comparison verification cannot be stronger than operand evidence")

    actual = assess_population_compatibility(baseline, candidate)
    if (
        comparison.population_compatibility is PopulationCompatibility.MATCHED
        and actual is not PopulationCompatibility.MATCHED
    ):
        raise ValueError("comparison population compatibility does not match operand metadata")
