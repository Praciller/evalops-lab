"""Conservative request pacing and circuit breaking for external pilots."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


class RateLimitStopError(RuntimeError):
    """Raised when provider quota pressure makes continued execution unsafe."""


class RateLimitCircuitBreakerError(RateLimitStopError):
    """Raised when repeated rate limits make continued execution unsafe."""


class DailyQuotaExhaustedError(RateLimitStopError):
    """Raised when the provider identifies a requests-per-day quota limit."""


@dataclass
class RateAwareRequestScheduler:
    """Pace requests and stop after repeated provider rate limits."""

    min_interval_seconds: float = 10.0
    max_consecutive_rate_limits: int = 3
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    last_request_at: float | None = field(default=None, init=False)
    consecutive_rate_limits: int = field(default=0, init=False)
    rate_limit_count: int = field(default=0, init=False)
    rate_limit_dimensions: list[str] = field(default_factory=list, init=False)
    _last_retry_after_seconds: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.min_interval_seconds < 0:
            raise ValueError("minimum request interval cannot be negative")
        if self.max_consecutive_rate_limits < 1:
            raise ValueError("maximum consecutive rate limits must be positive")

    def before_request(self) -> None:
        """Wait until the next request is outside the configured interval."""

        if self.last_request_at is not None:
            elapsed = self.clock() - self.last_request_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self.sleep(remaining)
        self.last_request_at = self.clock()

    def observe(
        self,
        error_class: str | None,
        *,
        retry_after_seconds: float | None = None,
        rate_limit_dimension: str | None = None,
    ) -> None:
        """Record a response and trip the breaker on consecutive 429s."""

        if error_class == "API_RATE_LIMIT":
            self.rate_limit_count += 1
            self.consecutive_rate_limits += 1
            self._last_retry_after_seconds = retry_after_seconds
            if rate_limit_dimension:
                self.rate_limit_dimensions.append(rate_limit_dimension)
            if rate_limit_dimension == "RPD":
                raise DailyQuotaExhaustedError("DAILY_QUOTA_EXHAUSTED")
            if self.consecutive_rate_limits >= self.max_consecutive_rate_limits:
                raise RateLimitCircuitBreakerError("RATE_LIMIT_STILL_BLOCKING")
        else:
            self.consecutive_rate_limits = 0
            self._last_retry_after_seconds = None

    def wait_before_retry(self, retry_after_seconds: float | None = None) -> None:
        """Honor provider delay while retaining the conservative default floor."""

        delay = max(
            self.min_interval_seconds,
            retry_after_seconds
            if retry_after_seconds is not None
            else self._last_retry_after_seconds or 0.0,
        )
        if delay > 0:
            self.sleep(delay)
