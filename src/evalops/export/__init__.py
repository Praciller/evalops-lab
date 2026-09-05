"""Safe, deterministic adapters for public Evidence Dashboard artifacts."""

from evalops.export.adapters import (
    adapt_evaluation_result,
    adapt_regression_report,
    build_public_index,
)
from evalops.export.models import (
    PUBLIC_EVIDENCE_SCHEMA_VERSION,
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
from evalops.export.serialization import (
    load_public_artifact,
    serialize_public_artifact,
    write_public_artifact,
)

__all__ = [
    "ClaimScope",
    "DataKind",
    "PUBLIC_EVIDENCE_SCHEMA_VERSION",
    "PublicArtifact",
    "PublicArtifactSummary",
    "PublicComparisonArtifactV1",
    "PublicComparisonMetric",
    "PublicEvidenceIndexV1",
    "PublicEvidenceRecord",
    "PublicFailure",
    "PublicRunMetadata",
    "PublicRunArtifactV1",
    "VerificationStatus",
    "adapt_evaluation_result",
    "adapt_regression_report",
    "build_public_index",
    "load_public_artifact",
    "serialize_public_artifact",
    "write_public_artifact",
]
