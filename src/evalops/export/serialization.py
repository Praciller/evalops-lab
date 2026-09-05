"""Canonical JSON serialization for public Evidence Contract artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalops.export.models import (
    PublicArtifact,
    PublicComparisonArtifactV1,
    PublicEvidenceIndexV1,
    PublicRunArtifactV1,
)


def serialize_public_artifact(artifact: PublicArtifact) -> str:
    """Serialize a validated artifact with stable formatting and key ordering."""

    return (
        json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_public_artifact(artifact: PublicArtifact, path: str | Path) -> str:
    serialized = serialize_public_artifact(artifact)
    Path(path).write_text(serialized, encoding="utf-8")
    return serialized


def load_public_artifact(payload: dict[str, Any]) -> PublicArtifact:
    """Validate one already-approved artifact for explicit index construction."""

    artifact_type = payload.get("artifact_type")
    if artifact_type == "run":
        return PublicRunArtifactV1.model_validate(payload)
    if artifact_type == "comparison":
        return PublicComparisonArtifactV1.model_validate(payload)
    if artifact_type == "index":
        return PublicEvidenceIndexV1.model_validate(payload)
    raise ValueError("unsupported public artifact_type")
