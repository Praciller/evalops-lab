"""Safe provenance continuity checks for multi-session model runs."""

from __future__ import annotations

from dataclasses import dataclass, field


class ModelVersionChangedError(RuntimeError):
    """Raised before accepting a prediction from a changed model version."""


@dataclass
class ModelVersionContinuity:
    """Track historical and resumed model versions without fabricating gaps."""

    historical_versions: set[str]
    resumed_versions: set[str] = field(default_factory=set)
    _failed: bool = field(default=False, init=False)

    @property
    def historical_status(self) -> str:
        return "AVAILABLE" if self.historical_versions else "UNAVAILABLE"

    @property
    def status(self) -> str:
        if self._failed:
            return "FAIL"
        if not self.historical_versions or not self.resumed_versions:
            return "UNVERIFIED"
        return "PASS"

    def observe(self, model_version: str | None) -> None:
        """Accept a version only when it matches known continuity constraints."""

        if not model_version:
            return
        if self.historical_versions and model_version not in self.historical_versions:
            self._failed = True
            raise ModelVersionChangedError("MODEL_VERSION_CHANGED_DURING_PILOT")
        if self.resumed_versions and model_version not in self.resumed_versions:
            self._failed = True
            raise ModelVersionChangedError("MODEL_VERSION_CHANGED_DURING_PILOT")
        self.resumed_versions.add(model_version)
