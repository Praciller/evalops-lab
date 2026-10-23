"""Evaluate comparability before allowing canonical retrieval regression claims."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from evalops.models.runs import EvaluationResult
from evalops.workspace.application.runs import RunSnapshot, _load_records
from evalops.workspace.comparison.models import (
    ComparisonCompatibility,
    ComparisonCompatibilityStatus,
    CompatibilityReason,
    RetrievalPopulationEvidence,
)
from evalops.workspace.ingestion.models import InputKind
from evalops.workspace.storage import WorkspaceStorageError, WorkspaceStore

# Local analogue of the frozen public POPULATION_FIELDS, with added annotation
# and evaluator configuration. System/prediction hashes deliberately differ.
POPULATION_CONFIG_FIELDS = (
    "annotation_policy",
    "benchmark",
    "dataset_name",
    "dataset_revision",
    "dataset_version",
    "evaluator_config",
    "evaluator_versions",
    "language",
    "quality_filter",
    "split",
    "top_k",
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def canonical_population_evidence(
    ground_truth: Mapping[str, Sequence[str]],
    predictions: Mapping[str, Sequence[str]],
) -> RetrievalPopulationEvidence:
    """Canonicalize source data; JSONL line order and relevance order cannot drift identity."""

    normalized_truth = [
        (query_id, sorted(set(ground_truth[query_id]))) for query_id in sorted(ground_truth)
    ]
    return RetrievalPopulationEvidence(
        ground_truth_fingerprint=_digest(normalized_truth),
        ground_truth_query_ids_fingerprint=_digest(sorted(ground_truth)),
        prediction_query_ids_fingerprint=_digest(sorted(predictions)),
        ground_truth_query_count=len(ground_truth),
        prediction_query_count=len(predictions),
    )


def load_verified_population(
    store: WorkspaceStore, snapshot: RunSnapshot
) -> RetrievalPopulationEvidence:
    """Read actual owned inputs through the authoritative hash-checking storage boundary."""

    expected = (
        (
            snapshot.ground_truth_input_id,
            snapshot.ground_truth_content_sha256,
            InputKind.RETRIEVAL_GROUND_TRUTH,
        ),
        (
            snapshot.predictions_input_id,
            snapshot.predictions_content_sha256,
            InputKind.RETRIEVAL_PREDICTIONS,
        ),
    )
    values: list[dict[str, list[str]]] = []
    for input_id, expected_sha, kind in expected:
        manifest = store.get_input(snapshot.workspace_id, input_id)
        if manifest.kind != kind or manifest.content_sha256 != expected_sha:
            raise WorkspaceStorageError("comparison input identity is invalid")
        data = store.read_input_bytes(snapshot.workspace_id, input_id)
        values.append(_load_records(data, kind))
    return canonical_population_evidence(values[0], values[1])


def _safe_difference(field: str, left: Any, right: Any) -> CompatibilityReason:
    """Never return raw dataset labels, query IDs, local paths or private configurations."""

    if field == "top_k":
        return CompatibilityReason(field=field, baseline=str(left), candidate=str(right))
    return CompatibilityReason(
        field=field,
        baseline="missing" if left is None else "present",
        candidate="missing" if right is None else "different",
    )


def assess_local_retrieval_compatibility(
    baseline_snapshot: RunSnapshot,
    baseline_result: EvaluationResult,
    candidate_snapshot: RunSnapshot,
    candidate_result: EvaluationResult,
    *,
    baseline_population: RetrievalPopulationEvidence | None = None,
    candidate_population: RetrievalPopulationEvidence | None = None,
) -> ComparisonCompatibility:
    """Fail closed on inconsistent metadata or absent verified population evidence.

    The population evidence must be derived server-side via load_verified_population().
    No client-supplied fingerprint can qualify as an authoritative comparison.
    """

    problems: list[CompatibilityReason] = []

    def mismatch(field: str, left: Any, right: Any) -> None:
        if left != right:
            problems.append(_safe_difference(field, left, right))

    mismatch(
        "run_schema_version", baseline_snapshot.schema_version, candidate_snapshot.schema_version
    )
    mismatch("workspace_id", baseline_snapshot.workspace_id, candidate_snapshot.workspace_id)
    mismatch("evaluation_type", baseline_result.evaluation_type, candidate_result.evaluation_type)
    if (
        baseline_result.evaluation_type != "retrieval"
        or candidate_result.evaluation_type != "retrieval"
    ):
        problems.append(
            _safe_difference(
                "retrieval_only", baseline_result.evaluation_type, candidate_result.evaluation_type
            )
        )
    for field in POPULATION_CONFIG_FIELDS:
        mismatch(
            field,
            getattr(baseline_snapshot.config, field),
            getattr(candidate_snapshot.config, field),
        )
    for label, snapshot, result in (
        ("baseline", baseline_snapshot, baseline_result),
        ("candidate", candidate_snapshot, candidate_result),
    ):
        if result.run != snapshot.config or result.run.run_id != snapshot.run_id:
            problems.append(_safe_difference(f"{label}_result_identity", None, "invalid"))

    if baseline_population is None or candidate_population is None:
        problems.append(
            _safe_difference("verified_population", baseline_population, candidate_population)
        )
    else:
        mismatch(
            "ground_truth_population",
            baseline_population.ground_truth_fingerprint,
            candidate_population.ground_truth_fingerprint,
        )
        mismatch(
            "query_population",
            baseline_population.ground_truth_query_ids_fingerprint,
            candidate_population.ground_truth_query_ids_fingerprint,
        )
        for label, evidence, result in (
            ("baseline", baseline_population, baseline_result),
            ("candidate", candidate_population, candidate_result),
        ):
            if (
                evidence.prediction_query_ids_fingerprint
                != evidence.ground_truth_query_ids_fingerprint
            ):
                problems.append(_safe_difference(f"{label}_prediction_coverage", None, "invalid"))
            if result.details.get("prediction_query_count") != evidence.prediction_query_count:
                problems.append(_safe_difference(f"{label}_prediction_count", None, "invalid"))

    reasons = sorted(problems, key=lambda item: item.field)
    return ComparisonCompatibility(
        status=(
            ComparisonCompatibilityStatus.NON_COMPARABLE
            if reasons
            else ComparisonCompatibilityStatus.COMPARABLE
        ),
        reasons=reasons,
    )
