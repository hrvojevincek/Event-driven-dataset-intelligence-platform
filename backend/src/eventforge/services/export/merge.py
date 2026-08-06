"""Merge annotation batches into model-ready JSONL."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from eventforge.db.models import AnnotationBatch, Asset, Job, Segment


@dataclass(frozen=True)
class ExportRecord:
    """One labeled segment row for JSONL export."""

    segment_id: uuid.UUID
    content: str
    labels: dict[str, str]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class MergeResult:
    """Merged export payload for persistence."""

    records: list[ExportRecord]
    jsonl: str
    segment_count: int


def _parse_batch_labels(
    labels_json: dict[str, Any] | str,
    *,
    batch_confidence: float | None = None,
) -> list[tuple[uuid.UUID, dict[str, str], float]]:
    """Parse AnnotationBatch.labels_json into per-segment label tuples.

    Accepts canonical segment-map shape ``{"<segment_id>": {...labels}}`` or the
    legacy ``{"segments": [{"segment_id", "labels", "confidence"}]}`` array.
    Canonical map entries use ``batch_confidence`` when per-segment confidence
    is not stored in ``labels_json``.
    """
    if isinstance(labels_json, str):
        try:
            parsed = json.loads(labels_json)
        except json.JSONDecodeError as exc:
            msg = "labels_json must be valid JSON"
            raise ValueError(msg) from exc
    else:
        parsed = labels_json

    if isinstance(parsed, dict) and "segments" in parsed:
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list):
            msg = "labels_json segments must be a list"
            raise ValueError(msg)
        labeled: list[tuple[uuid.UUID, dict[str, str], float]] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            segment_id = item.get("segment_id")
            labels = item.get("labels")
            if not isinstance(segment_id, str) or not isinstance(labels, dict):
                continue
            normalized = {
                str(key): str(value).strip()
                for key, value in labels.items()
                if isinstance(value, str) and value.strip()
            }
            confidence_raw = item.get("confidence", 0.0)
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = 0.0
            labeled.append((uuid.UUID(segment_id), normalized, confidence))
        return labeled

    if isinstance(parsed, dict):
        fallback_confidence = 0.0
        if batch_confidence is not None:
            try:
                fallback_confidence = float(batch_confidence)
            except (TypeError, ValueError):
                fallback_confidence = 0.0
        legacy: list[tuple[uuid.UUID, dict[str, str], float]] = []
        for key, value in parsed.items():
            if not isinstance(value, dict):
                continue
            try:
                segment_id = uuid.UUID(str(key))
            except ValueError:
                continue
            normalized = {
                str(field): str(field_value).strip()
                for field, field_value in value.items()
                if isinstance(field_value, str) and field_value.strip()
            }
            legacy.append((segment_id, normalized, fallback_confidence))
        return legacy

    msg = "labels_json must be a segment map or labeler segments array"
    raise ValueError(msg)


def _record_to_line(record: ExportRecord) -> str:
    return json.dumps(
        {
            "segment_id": str(record.segment_id),
            "content": record.content,
            "labels": record.labels,
            "provenance": record.provenance,
        },
        ensure_ascii=False,
    )


def merge_batches_to_jsonl(
    project: Job,
    batches: list[AnnotationBatch],
    segments: list[Segment],
    assets_by_id: dict[uuid.UUID, Asset],
    *,
    annotator: str | None = None,
) -> MergeResult:
    """Combine labeled batches into ordered JSONL for a project."""
    labels_by_segment: dict[uuid.UUID, tuple[dict[str, str], float]] = {}
    for batch in batches:
        batch_confidence = float(batch.confidence) if batch.confidence is not None else None
        for segment_id, labels, confidence in _parse_batch_labels(
            batch.labels_json,
            batch_confidence=batch_confidence,
        ):
            labels_by_segment[segment_id] = (labels, confidence)

    ordered_segments = sorted(
        segments,
        key=lambda segment: (segment.asset_id, segment.segment_index),
    )
    records: list[ExportRecord] = []
    for segment in ordered_segments:
        label_entry = labels_by_segment.get(segment.id)
        if label_entry is None:
            continue
        labels, confidence = label_entry
        asset = assets_by_id.get(segment.asset_id)
        records.append(
            ExportRecord(
                segment_id=segment.id,
                content=segment.content,
                labels=labels,
                provenance={
                    "asset_filename": asset.filename if asset is not None else "unknown",
                    "project_id": str(project.id),
                    "annotator": annotator or "unknown",
                    "confidence": round(confidence, 4),
                },
            )
        )

    jsonl = "\n".join(_record_to_line(record) for record in records)
    if jsonl:
        jsonl += "\n"
    return MergeResult(records=records, jsonl=jsonl, segment_count=len(records))
