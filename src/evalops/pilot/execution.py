"""Resumable, budgeted, sequential Phase 5A execution."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from evalops.evaluators.judge.evaluator import JudgeEvaluationTrace
from evalops.pilot.models import PilotManifest, PilotRunRecord, serialize_state_record


class PilotRequestLimitError(RuntimeError):
    """Raised before an external call would exceed the global request ceiling."""


class RequestBudget:
    """Process-local hard request counter for all preflight/pilot/repeat calls."""

    def __init__(self, max_requests: int = 300) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        self.max_requests = max_requests
        self.requests_used = 0

    def reserve(self) -> None:
        if self.requests_used >= self.max_requests:
            raise PilotRequestLimitError(
                f"Phase 5A request ceiling {self.max_requests} would be exceeded"
            )
        self.requests_used += 1


class PilotStateStore:
    """Atomic JSON store keyed by provider and example ID."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        if self.path.is_file():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("records", {}) if isinstance(payload, dict) else {}
            if not isinstance(records, dict):
                raise ValueError("pilot state records must be an object")
            self._records = records

    @staticmethod
    def _key(provider: str, example_id: str) -> str:
        return f"{provider}:{example_id}"

    def is_successful(self, provider: str, example_id: str) -> bool:
        return self._records.get(self._key(provider, example_id), {}).get("status") == "SUCCESS"

    def get(self, provider: str, example_id: str) -> PilotRunRecord | None:
        payload = self._records.get(self._key(provider, example_id))
        return PilotRunRecord.model_validate(payload) if payload else None

    def upsert(self, record: PilotRunRecord) -> None:
        self._records[self._key(record.provider, record.example_id)] = serialize_state_record(
            record
        )
        self._write_atomic()

    def _write_atomic(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {"schema_version": "phase5a-state-v1", "records": self._records}
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


ProviderEvaluator = Callable[[str, str, str], JudgeEvaluationTrace]
RETRYABLE_ERRORS = {"API_RATE_LIMIT", "API_SERVER_ERROR", "API_TIMEOUT"}


def assert_matching_ids(expected_ids: set[str], *observed_id_sets: set[str]) -> None:
    """Reject missing/extra populations instead of turning missing calls negative."""

    if any(observed != expected_ids for observed in observed_id_sets):
        raise ValueError("provider comparison requires identical example IDs")


def run_provider_pilot(
    manifest: PilotManifest,
    examples: Mapping[str, tuple[str, str]],
    provider_evaluators: Mapping[str, ProviderEvaluator],
    state_store: PilotStateStore,
    budget: RequestBudget,
    *,
    max_retries: int = 2,
    retry_sleep: Callable[[float], None] = time.sleep,
    parse_regenerations: Mapping[str, int] | None = None,
) -> list[PilotRunRecord]:
    """Evaluate exact manifest IDs sequentially with bounded transient retries."""

    expected_ids = set(manifest.example_ids)
    if not expected_ids.issubset(examples):
        raise ValueError("pilot examples do not contain every manifest ID")
    results: list[PilotRunRecord] = []
    for provider in sorted(provider_evaluators):
        evaluator = provider_evaluators[provider]
        for example_id in manifest.example_ids:
            if state_store.is_successful(provider, example_id):
                previous = state_store.get(provider, example_id)
                if previous is not None:
                    results.append(previous)
                continue
            context, response = examples[example_id]
            retry_count = 0
            regeneration_count = 0
            while True:
                budget.reserve()
                trace = evaluator(context, response, example_id)
                if (
                    trace.prediction is None
                    and trace.api_success
                    and trace.error_class in {"PARSE_ERROR", "SCHEMA_VALIDATION_ERROR"}
                    and regeneration_count < (parse_regenerations or {}).get(provider, 0)
                ):
                    regeneration_count += 1
                    continue
                attempt = retry_count + regeneration_count + 1
                record = PilotRunRecord(
                    provider=provider,
                    example_id=example_id,
                    attempt=attempt,
                    status="SUCCESS" if trace.prediction is not None else "FAILED",
                    trace=trace,
                )
                state_store.upsert(record)
                if trace.prediction is not None:
                    results.append(record)
                    break
                if trace.error_class not in RETRYABLE_ERRORS or retry_count >= max_retries:
                    results.append(record)
                    break
                retry_count += 1
                retry_sleep(min(2.0, 0.1 * (2 ** (retry_count - 1))))
    return results
