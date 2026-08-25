"""Deterministic HHEM premise construction for each RAGTruth task family."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from evalops.models.hallucination import HallucinationExample

HHEM_CONTEXT_STRATEGY = "ragtruth-source-context-v1"


class HHEMContext(BaseModel):
    """A model-ready premise/hypothesis pair with its construction provenance."""

    model_config = ConfigDict(extra="forbid")

    example_id: str
    task_type: str
    premise: str
    hypothesis: str
    strategy: str = HHEM_CONTEXT_STRATEGY


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_hhem_context(example: HallucinationExample) -> HHEMContext:
    """Build only from source evidence and response text, never labels or prompts."""

    task_type = example.task_type.casefold()
    if task_type == "qa":
        source_info = example.source_info
        if isinstance(source_info, dict) and isinstance(source_info.get("passages"), str):
            premise = source_info["passages"]
        else:
            premise = example.source_context
    elif task_type == "summary":
        premise = (
            example.source_info if isinstance(example.source_info, str) else example.source_context
        )
    elif task_type == "data2txt":
        premise = _stable_json(example.source_info)
    else:
        premise = example.source_context
    return HHEMContext(
        example_id=example.example_id,
        task_type=example.task_type,
        premise=premise,
        hypothesis=example.response,
    )
