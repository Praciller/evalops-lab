from __future__ import annotations

import pytest

from evalops.pilot.provenance import ModelVersionChangedError, ModelVersionContinuity


def test_missing_historical_model_version_is_reported_as_unverified() -> None:
    continuity = ModelVersionContinuity(historical_versions=set())

    continuity.observe("gemini-version-a")

    assert continuity.historical_status == "UNAVAILABLE"
    assert continuity.status == "UNVERIFIED"
    assert continuity.resumed_versions == {"gemini-version-a"}


def test_resumed_model_version_must_remain_constant() -> None:
    continuity = ModelVersionContinuity(historical_versions=set())
    continuity.observe("gemini-version-a")

    with pytest.raises(ModelVersionChangedError, match="MODEL_VERSION_CHANGED_DURING_PILOT"):
        continuity.observe("gemini-version-b")


def test_known_historical_model_version_rejects_a_different_resume_version() -> None:
    continuity = ModelVersionContinuity(historical_versions={"gemini-version-a"})

    with pytest.raises(ModelVersionChangedError, match="MODEL_VERSION_CHANGED_DURING_PILOT"):
        continuity.observe("gemini-version-b")

    assert continuity.status == "FAIL"
