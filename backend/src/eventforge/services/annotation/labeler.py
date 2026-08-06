"""LLM labeling of segment batches against a project label schema."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eventforge.db.models import Segment
from eventforge.events.schemas import WORKER_NAME_ANNOTATION
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMMessage

logger = logging.getLogger(__name__)

_LABELER_SYSTEM = (
    "You label text segments for a dataset annotation pipeline. "
    "Respond with a JSON object only — no markdown fences or commentary. "
    'Shape: {"segments": [{"segment_index": 0, "labels": {...}, "confidence": 0.0-1.0}]}. '
    "Use segment_index as the 0-based index into the provided segments. "
    "labels must match the provided JSON Schema properties (string values). "
    "confidence is your certainty for that segment (0.0–1.0)."
)

_LOW_CONFIDENCE = Decimal("0.3000")
_DEFAULT_CONFIDENCE = Decimal("0.8500")


@dataclass(frozen=True)
class SegmentLabels:
    """Labels and confidence for one segment."""

    segment_id: uuid.UUID
    labels: dict[str, str]
    confidence: Decimal


@dataclass(frozen=True)
class LabelBatchResult:
    """Validated labels for a whole annotation task."""

    segment_labels: list[SegmentLabels]
    labels_json: dict[str, Any]
    confidence: Decimal
    low_confidence: bool


def _strip_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def _required_fields(label_schema: dict[str, Any]) -> list[str]:
    required = label_schema.get("required")
    if isinstance(required, list) and required:
        return [str(field) for field in required]
    properties = label_schema.get("properties", {})
    if isinstance(properties, dict):
        return [str(field) for field in properties]
    return []


def _normalize_labels(raw_labels: Any, required: list[str]) -> dict[str, str] | None:
    if not isinstance(raw_labels, dict):
        return None
    labels: dict[str, str] = {}
    for field in required:
        value = raw_labels.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        labels[field] = value.strip()
    return labels


def _parse_confidence(raw: Any) -> Decimal:
    try:
        value = Decimal(str(raw))
    except Exception:
        return _DEFAULT_CONFIDENCE
    if value < 0:
        return Decimal("0.0000")
    if value > 1:
        return Decimal("1.0000")
    return value.quantize(Decimal("0.0001"))


def _build_prompt(
    *,
    instructions: str,
    label_schema: dict[str, Any],
    segments: list[Segment],
) -> str:
    blocks = [
        f"Instructions: {instructions}",
        "",
        "Label schema (JSON Schema):",
        json.dumps(label_schema, indent=2),
        "",
        "Segments:",
    ]
    for index, segment in enumerate(segments):
        blocks.extend([f"[{index}]", segment.content, ""])
    blocks.append("Return one labels object per segment_index covering every required field.")
    return "\n".join(blocks)


def _fallback_labels(
    segments: list[Segment],
    required: list[str],
) -> list[SegmentLabels]:
    empty = {field: "unknown" for field in required}
    return [
        SegmentLabels(segment_id=segment.id, labels=dict(empty), confidence=_LOW_CONFIDENCE)
        for segment in segments
    ]


def _parse_label_response(
    content: str,
    segments: list[Segment],
    label_schema: dict[str, Any],
) -> list[SegmentLabels]:
    data = json.loads(_strip_fences(content))
    if not isinstance(data, dict):
        msg = "Labeler response must be a JSON object"
        raise ValueError(msg)

    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        msg = "Labeler response must include a segments array"
        raise ValueError(msg)

    required = _required_fields(label_schema)
    by_index: dict[int, SegmentLabels] = {}
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        index = item.get("segment_index")
        if not isinstance(index, int) or index < 0 or index >= len(segments):
            continue
        labels = _normalize_labels(item.get("labels"), required)
        if labels is None:
            continue
        by_index[index] = SegmentLabels(
            segment_id=segments[index].id,
            labels=labels,
            confidence=_parse_confidence(item.get("confidence", _DEFAULT_CONFIDENCE)),
        )

    if len(by_index) != len(segments):
        msg = "Labeler response missing labels for one or more segments"
        raise ValueError(msg)

    return [by_index[index] for index in range(len(segments))]


def build_labels_json(segment_labels: list[SegmentLabels]) -> dict[str, Any]:
    """Serialize per-segment labels for AnnotationBatch.labels_json."""
    return {str(item.segment_id): dict(item.labels) for item in segment_labels}


def batch_confidence(segment_labels: list[SegmentLabels]) -> Decimal:
    """Aggregate batch confidence as the minimum per-segment confidence."""
    if not segment_labels:
        return _LOW_CONFIDENCE
    return min(item.confidence for item in segment_labels)


async def label_segments(
    llm_client: LLMClient,
    *,
    project_id: uuid.UUID,
    instructions: str,
    segments: list[Segment],
    label_schema: dict[str, Any],
) -> LabelBatchResult:
    """Call the LLM to label segments and validate against the label schema."""
    if not segments:
        msg = "At least one segment is required for annotation"
        raise ValueError(msg)

    required = _required_fields(label_schema)
    if not required:
        msg = "Label schema must define required fields or properties"
        raise ValueError(msg)

    prompt = _build_prompt(
        instructions=instructions,
        label_schema=label_schema,
        segments=segments,
    )
    result = await llm_client.complete(
        [
            LLMMessage(role="system", content=_LABELER_SYSTEM),
            LLMMessage(role="user", content=prompt),
        ],
        job_id=project_id,
        agent_name=WORKER_NAME_ANNOTATION,
    )

    try:
        segment_labels = _parse_label_response(result.content, segments, label_schema)
    except (json.JSONDecodeError, ValueError):
        logger.exception(
            "Annotation label parse failed; using low-confidence fallback",
            extra={"project_id": str(project_id), "segment_count": len(segments)},
        )
        segment_labels = _fallback_labels(segments, required)

    confidence = batch_confidence(segment_labels)
    return LabelBatchResult(
        segment_labels=segment_labels,
        labels_json=build_labels_json(segment_labels),
        confidence=confidence,
        low_confidence=confidence < Decimal("0.5000"),
    )
