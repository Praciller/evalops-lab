"""Allowlist-oriented safety checks for public Evidence artifacts."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

_UNSAFE_NAME = re.compile(
    r"^(?:api[_-]?key|authorization|bearer|password|secret|token)(?:[_-]?value)?$", re.I
)
_UNSAFE_TEXT = re.compile(
    r"(?:api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]", re.I
)
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def safe_identifier(value: str, *, field: str) -> str:
    """Accept an identifier that cannot be interpreted as a filesystem path."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized in {".", ".."}:
        raise ValueError(f"{field} must be a safe identifier, not a path")
    if any(character in normalized for character in ("/", "\\")):
        raise ValueError(f"{field} must be a safe identifier, not a path")
    if _UNSAFE_NAME.search(normalized) or _UNSAFE_TEXT.search(normalized):
        raise ValueError(f"{field} contains unsafe secret-like text")
    return normalized


def safe_public_text(value: str, *, field: str, max_length: int = 500) -> str:
    """Reject secret-like values, paths, and control characters at publication time."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field} exceeds the public text limit")
    if (
        _UNSAFE_NAME.search(normalized)
        or _UNSAFE_TEXT.search(normalized)
        or _WINDOWS_PATH.match(normalized)
        or normalized.startswith("/")
    ):
        raise ValueError(f"{field} contains unsafe public text")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in normalized):
        raise ValueError(f"{field} contains control characters")
    return normalized


def safe_optional_text(value: str | None, *, field: str, max_length: int = 500) -> str | None:
    if value is None:
        return None
    return safe_public_text(value, field=field, max_length=max_length)


def stable_metrics(value: Mapping[str, Any], *, field: str = "metrics") -> dict[str, float]:
    """Validate finite metrics and return them in canonical key order."""

    result: dict[str, float] = {}
    for name, raw_value in sorted(value.items(), key=lambda item: str(item[0])):
        metric_name = safe_identifier(str(name), field=f"{field} name")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"{field}.{metric_name} must be numeric")
        numeric_value = float(raw_value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"{field}.{metric_name} must be finite")
        result[metric_name] = numeric_value
    return result


def stable_floats(value: list[float], *, field: str) -> list[float]:
    result: list[float] = []
    for raw_value in value:
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"{field} must contain only numeric values")
        numeric_value = float(raw_value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"{field} must contain only finite values")
        result.append(numeric_value)
    return result


def safe_string_map(value: Mapping[str, str], *, field: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, raw_value in sorted(value.items(), key=lambda item: str(item[0])):
        key = safe_identifier(str(name), field=f"{field} key")
        result[key] = safe_public_text(str(raw_value), field=f"{field}.{key}")
    return result
