from __future__ import annotations

from scripts.run_phase5a_pilot import (
    OFFICIAL_PROVIDER_NAMES,
    estimate_request_count,
    preflight_request_count,
)


def test_official_provider_scope_excludes_non_reproducible_or_blocked_paths() -> None:
    assert OFFICIAL_PROVIDER_NAMES == ("gemini", "okmd")


def test_request_estimate_respects_the_300_request_ceiling() -> None:
    assert estimate_request_count(120, include_consistency=False) == 249
    assert estimate_request_count(120, include_consistency=True) == 297
    assert estimate_request_count(121, include_consistency=True) == 299


def test_preflight_request_count_preserves_real_requests_across_restarts() -> None:
    assert preflight_request_count(0) == 9
    assert preflight_request_count(2) == 11
