"""Adapters from internal evaluation results to the public Evidence Contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from evalops.export.models import (
    ClaimScope,
    DataKind,
    PublicArtifact,
    PublicArtifactSummary,
    PublicComparisonArtifactV1,
    PublicComparisonMetric,
    PublicEvidenceIndexV1,
    PublicEvidenceRecord,
    PublicFailure,
    PublicRunArtifactV1,
    PublicRunMetadata,
    VerificationStatus,
)
from evalops.export.policy import safe_identifier, stable_metrics
from evalops.models.runs import EvaluationResult
from evalops.regression.comparison import RegressionReport


def _as_evaluation_result(source: EvaluationResult | Mapping[str, Any]) -> EvaluationResult:
    if isinstance(source, EvaluationResult):
        return source
    return EvaluationResult.model_validate(source)


def _as_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must contain only strings")
    return [safe_identifier(item, field=field) for item in value]


def _float_list(value: object, *, field: str) -> list[float]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise ValueError(f"{field} must contain only numeric values")
    return [float(item) for item in value]


def _sort_failures(failures: Sequence[PublicFailure]) -> list[PublicFailure]:
    return sorted(
        failures,
        key=lambda failure: (
            failure.record_ref,
            failure.category,
            failure.failure_class or "",
        ),
    )


def _public_run_metadata(source: EvaluationResult) -> PublicRunMetadata:
    run = source.run
    return PublicRunMetadata(
        evaluation_type=source.evaluation_type,
        run_id=run.run_id,
        dataset_name=run.dataset_name,
        dataset_version=run.dataset_version,
        dataset_revision=run.dataset_revision,
        system_name=run.system_name,
        model=run.model,
        model_provider=run.model_provider,
        benchmark=run.benchmark,
        language=run.language,
        split=run.split,
        retriever=run.retriever,
        retriever_version=run.retriever_version,
        tokenization_strategy=run.tokenization_strategy,
        top_k=run.top_k,
        evaluator_versions=run.evaluator_versions,
        random_seed=run.random_seed,
        timestamp=run.timestamp,
        git_commit=run.git_commit,
    )


def _public_evidence(
    source: EvaluationResult,
    *,
    data_kind: DataKind,
) -> tuple[list[PublicEvidenceRecord], list[PublicFailure]]:
    details = source.details
    raw_per_query = details.get("per_query")
    if raw_per_query is None or data_kind is not DataKind.SYNTHETIC_FIXTURE:
        return [], _sort_failures(
            [
                PublicFailure(
                    record_ref=f"run:{source.run.run_id}",
                    category=str(failure.category),
                    failure_class=(str(failure.failure_class) if failure.failure_class else None),
                )
                for failure in source.failures
            ]
        )
    per_query = _as_mapping(raw_per_query, field="details.per_query")
    evidence: list[PublicEvidenceRecord] = []
    failures: list[PublicFailure] = []
    for raw_record_ref, raw_record in sorted(per_query.items(), key=lambda item: str(item[0])):
        record = _as_mapping(raw_record, field=f"details.per_query.{raw_record_ref}")
        if not isinstance(raw_record_ref, str):
            raise ValueError("record_ref must be a string")
        record_ref = safe_identifier(raw_record_ref, field="record_ref")
        raw_metrics = record.get("metrics", {})
        metrics = stable_metrics(_as_mapping(raw_metrics, field="per-query metrics"))
        raw_metrics_by_k = record.get("metrics_by_k", {})
        metrics_by_k: dict[str, dict[str, float]] = {}
        if raw_metrics_by_k:
            metrics_by_k = {
                str(key): stable_metrics(_as_mapping(value, field="metrics_by_k"))
                for key, value in sorted(
                    _as_mapping(raw_metrics_by_k, field="metrics_by_k").items(),
                    key=lambda item: str(item[0]),
                )
            }
        category_value = record.get(
            "failure_category",
            _as_mapping(record.get("classification", {}), field="classification").get(
                "category", "PASS"
            ),
        )
        if not isinstance(category_value, str):
            raise ValueError("failure_category must be a string")
        category = category_value
        evidence.append(
            PublicEvidenceRecord(
                record_ref=record_ref,
                metrics=metrics,
                metrics_by_k=metrics_by_k,
                failure_category=category,
                retrieved_document_ids=_string_list(
                    record.get("retrieved_document_ids"), field="retrieved_document_ids"
                ),
                relevant_document_ids=_string_list(
                    record.get("relevant_document_ids"), field="relevant_document_ids"
                ),
                scores=_float_list(record.get("scores"), field="scores"),
            )
        )
        if category != "PASS":
            classification = _as_mapping(record.get("classification", {}), field="classification")
            failure_class = classification.get("failure_class")
            if failure_class is not None and not isinstance(failure_class, str):
                raise ValueError("failure_class must be a string or null")
            failures.append(
                PublicFailure(
                    record_ref=record_ref,
                    category=category,
                    failure_class=failure_class,
                )
            )
    return evidence, _sort_failures(failures)


def adapt_evaluation_result(
    source: EvaluationResult | Mapping[str, Any],
    *,
    artifact_id: str,
    verification_status: VerificationStatus,
    data_kind: DataKind,
    claim_scope: ClaimScope,
    limitations: Sequence[str] = (),
) -> PublicRunArtifactV1:
    """Adapt one explicit result source without passing through ``details`` wholesale."""

    result = _as_evaluation_result(source)
    evidence, failures = _public_evidence(result, data_kind=data_kind)
    if not evidence and result.failures and data_kind is DataKind.SYNTHETIC_FIXTURE:
        failures = _sort_failures(
            [
                PublicFailure(
                    record_ref=f"run:{result.run.run_id}",
                    category=str(failure.category),
                    failure_class=(str(failure.failure_class) if failure.failure_class else None),
                )
                for failure in result.failures
            ]
        )
    return PublicRunArtifactV1(
        artifact_id=artifact_id,
        verification_status=verification_status,
        data_kind=data_kind,
        claim_scope=claim_scope,
        limitations=list(limitations),
        run=_public_run_metadata(result),
        metrics=stable_metrics(result.metrics),
        failures=failures,
        evidence=evidence,
    )


def adapt_regression_report(
    source: RegressionReport | Mapping[str, Any],
    *,
    artifact_id: str,
    baseline_artifact_id: str,
    candidate_artifact_id: str,
    verification_status: VerificationStatus,
    data_kind: DataKind,
    claim_scope: ClaimScope,
    limitations: Sequence[str] = (),
    population_compatibility: str | None = None,
) -> PublicComparisonArtifactV1:
    """Normalize only the standard metric regression report for public use."""

    if isinstance(source, RegressionReport):
        report = source
    else:
        report = RegressionReport.model_validate(
            {
                "passed": source.get("passed"),
                "comparisons": source.get("comparisons"),
            }
        )
    comparisons = [
        PublicComparisonMetric(
            metric_name=comparison.metric_name,
            direction=comparison.direction,
            baseline_value=comparison.baseline,
            candidate_value=comparison.current,
            delta=comparison.delta,
            status=comparison.status,
            reason=comparison.reason,
        )
        for comparison in sorted(report.comparisons, key=lambda item: item.metric_name)
    ]
    baseline_run_id = source.get("baseline_run_id") if isinstance(source, Mapping) else None
    candidate_run_id = source.get("candidate_run_id") if isinstance(source, Mapping) else None
    return PublicComparisonArtifactV1(
        artifact_id=artifact_id,
        verification_status=verification_status,
        data_kind=data_kind,
        claim_scope=claim_scope,
        limitations=list(limitations),
        baseline_artifact_id=baseline_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        baseline_run_id=str(baseline_run_id) if baseline_run_id is not None else None,
        candidate_run_id=str(candidate_run_id) if candidate_run_id is not None else None,
        passed=report.passed,
        comparisons=comparisons,
        population_compatibility=population_compatibility,
    )


def build_public_index(artifacts: Sequence[PublicArtifact]) -> PublicEvidenceIndexV1:
    """Build an index from an explicit artifact list; no filesystem discovery occurs."""

    summaries: list[PublicArtifactSummary] = []
    for artifact in artifacts:
        if isinstance(artifact, PublicRunArtifactV1):
            summaries.append(
                PublicArtifactSummary(
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    run_id=artifact.run.run_id,
                    dataset_name=artifact.run.dataset_name,
                    evaluation_type=artifact.run.evaluation_type,
                    verification_status=artifact.verification_status,
                    data_kind=artifact.data_kind,
                    claim_scope=artifact.claim_scope,
                    metrics=artifact.metrics,
                )
            )
        elif isinstance(artifact, PublicComparisonArtifactV1):
            summaries.append(
                PublicArtifactSummary(
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    run_id=artifact.candidate_run_id,
                    verification_status=artifact.verification_status,
                    data_kind=artifact.data_kind,
                    claim_scope=artifact.claim_scope,
                )
            )
        else:
            raise ValueError("public indexes may contain runs and comparisons, not nested indexes")
    return PublicEvidenceIndexV1(
        artifact_id="public-evidence-index-v1",
        verification_status=VerificationStatus.VERIFIED,
        data_kind=DataKind.CURATED_DATASET,
        claim_scope=ClaimScope.PROTOCOL_SPECIFIC,
        artifacts=sorted(summaries, key=lambda item: item.artifact_id),
    )
