"""Span comparison primitives kept separate from response-level classification."""

from __future__ import annotations

Span = tuple[int, int]


def exact_span_match(left: Span, right: Span) -> bool:
    return left == right


def character_overlap(left: Span, right: Span) -> int:
    return max(0, min(left[1], right[1]) - max(left[0], right[0]))


def character_iou(left: Span, right: Span) -> float:
    intersection = character_overlap(left, right)
    union = (left[1] - left[0]) + (right[1] - right[0]) - intersection
    return intersection / union if union else 0.0
