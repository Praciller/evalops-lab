"""Official RAGTruth JSONL adapter into generic hallucination models."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalops.models.hallucination import (
    DatasetAnnotationIssue,
    HallucinationDataset,
    HallucinationExample,
    HallucinationSpan,
)


def _iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    file_path = Path(path)
    with file_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: {error}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"could not parse {file_path.name} line {line_number}: expected an object"
                )
            yield record


def _source_context(source_info: Any) -> str:
    if isinstance(source_info, str):
        return source_info
    if isinstance(source_info, dict) and isinstance(source_info.get("passages"), str):
        # QA prompts contain the question as well as the evidence. The evaluator
        # must receive the evidence, not the query wording or prompt metadata.
        return source_info["passages"]
    return json.dumps(source_info, ensure_ascii=False, sort_keys=True)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _parse_labels(value: Any, *, record_id: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"response '{record_id}' labels are not valid JSON") from error
    if not isinstance(value, list) or any(not isinstance(label, dict) for label in value):
        raise ValueError(f"response '{record_id}' labels must be a list of objects")
    return value


def _normalize_span(
    label: dict[str, Any], response: str, *, record_id: str, span_index: int
) -> HallucinationSpan:
    try:
        start = int(label["start"])
        end = int(label["end"])
        text = str(label["text"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"response '{record_id}' label {span_index} requires integer start/end and text"
        ) from error
    issues: list[str] = []
    if end < start:
        issues.append("END_BEFORE_START")
    if end > len(response):
        issues.append("END_OUT_OF_RANGE")
    if start <= end <= len(response) and response[start:end] != text:
        issues.append("TEXT_OFFSET_MISMATCH")
    if start > len(response):
        issues.append("START_OUT_OF_RANGE")
    try:
        return HallucinationSpan(
            start=start,
            end=end,
            text=text,
            label_type=str(label.get("label_type", "unknown")),
            due_to_null=_bool_value(label.get("due_to_null", False)),
            implicit_true=_bool_value(label.get("implicit_true", False)),
            meta=label.get("meta"),
            offset_valid=not issues,
            validation_issues=issues,
        )
    except ValidationError as error:
        raise ValueError(
            f"response '{record_id}' label {span_index} is invalid: {error}"
        ) from error


def load_ragtruth_dataset(
    response_path: str | Path,
    source_info_path: str | Path,
    *,
    split: str | None = None,
    source_revision: str = "unknown",
) -> HallucinationDataset:
    """Load official RAGTruth response/source JSONL without changing annotations."""

    sources: dict[str, dict[str, Any]] = {}
    for record in _iter_jsonl(source_info_path):
        try:
            source_id = str(record["source_id"])
            task_type = str(record["task_type"])
            source_info = record["source_info"]
            source = str(record.get("source", ""))
            prompt = str(record.get("prompt", ""))
        except (KeyError, TypeError) as error:
            raise ValueError(f"source record is missing a required field: {error}") from error
        if source_id in sources:
            raise ValueError(f"duplicate source ID '{source_id}'")
        sources[source_id] = {
            "source_id": source_id,
            "task_type": task_type,
            "source": source,
            "source_info": source_info,
            "prompt": prompt,
            "raw": record,
        }

    examples: list[HallucinationExample] = []
    issues: list[DatasetAnnotationIssue] = []
    seen_response_ids: set[str] = set()
    for record in _iter_jsonl(response_path):
        try:
            example_id = str(record["id"])
            source_id = str(record["source_id"])
            response = str(record["response"])
            record_split = str(record["split"])
            quality = str(record.get("quality", "good"))
        except (KeyError, TypeError) as error:
            raise ValueError(f"response record is missing a required field: {error}") from error
        if example_id in seen_response_ids:
            raise ValueError(f"duplicate response ID '{example_id}'")
        seen_response_ids.add(example_id)
        if split is not None and record_split != split:
            continue
        if source_id not in sources:
            raise ValueError(f"response '{example_id}' references unknown source ID '{source_id}'")
        source_record = sources[source_id]
        labels = _parse_labels(record.get("labels", []), record_id=example_id)
        spans = [
            _normalize_span(label, response, record_id=example_id, span_index=index)
            for index, label in enumerate(labels)
        ]
        for span_index, span in enumerate(spans):
            for issue_code in span.validation_issues:
                issues.append(
                    DatasetAnnotationIssue(
                        code=issue_code,
                        message=(
                            f"span {span_index} in response '{example_id}' does not exactly "
                            "match its upstream character offsets"
                        ),
                        record_id=example_id,
                    )
                )
        try:
            examples.append(
                HallucinationExample(
                    example_id=example_id,
                    source_id=source_id,
                    task_type=source_record["task_type"],
                    source_name=source_record["source"],
                    source_context=_source_context(source_record["source_info"]),
                    source_info=source_record["source_info"],
                    prompt=source_record["prompt"],
                    response=response,
                    spans=spans,
                    split=record_split,
                    quality=quality,
                    model=(str(record["model"]) if record.get("model") is not None else None),
                    temperature=(
                        float(record["temperature"])
                        if record.get("temperature") is not None
                        else None
                    ),
                    raw_response=record,
                    raw_source=source_record["raw"],
                )
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise ValueError(f"response '{example_id}' could not be normalized: {error}") from error

    return HallucinationDataset(
        examples=examples,
        source_revision=source_revision,
        validation_issues=issues,
    )
