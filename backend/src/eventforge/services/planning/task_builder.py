"""Build annotation tasks from preprocessed segments and project schema."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from eventforge.db.models import AnnotationTask, Job, Segment
from eventforge.services.intake.templates import (
    DOCUMENT_CLASSIFICATION_TEMPLATE,
    SUPPORT_CALL_TEMPLATE,
)
from eventforge.services.planning.schema_templates import (
    load_label_schema,
    segments_per_task_for_template,
)


@dataclass(frozen=True)
class PlannedTask:
    """One annotation task ready to persist."""

    task_index: int
    instructions: str
    segment_ids: list[uuid.UUID]
    segment_ids_json: str


def build_annotation_tasks(
    job: Job,
    segments: list[Segment],
    *,
    segments_per_task: int | None = None,
) -> list[PlannedTask]:
    """Batch ordered segments into annotation tasks for the project's label schema."""
    if not segments:
        msg = "At least one segment is required to plan annotation tasks"
        raise ValueError(msg)

    label_schema = load_label_schema(job.schema_json, job.schema_template)
    batch_size = segments_per_task or segments_per_task_for_template(job.schema_template)
    if batch_size < 1:
        msg = "segments_per_task must be >= 1"
        raise ValueError(msg)

    instructions = _build_instructions(label_schema, job.schema_template)
    ordered = sorted(segments, key=lambda segment: (segment.asset_id, segment.segment_index))

    planned: list[PlannedTask] = []
    for task_index, start in enumerate(range(0, len(ordered), batch_size)):
        batch = ordered[start : start + batch_size]
        segment_ids = [segment.id for segment in batch]
        planned.append(
            PlannedTask(
                task_index=task_index,
                instructions=instructions,
                segment_ids=segment_ids,
                segment_ids_json=_encode_segment_payload(
                    segment_ids=segment_ids,
                    label_schema=label_schema,
                    schema_template=job.schema_template,
                ),
            )
        )
    return planned


def annotation_tasks_from_planned(
    job_id: uuid.UUID,
    planned: list[PlannedTask],
) -> list[AnnotationTask]:
    """Materialize ORM rows from planned tasks."""
    return [
        AnnotationTask(
            job_id=job_id,
            task_index=task.task_index,
            instructions=task.instructions,
            segment_ids_json=task.segment_ids_json,
        )
        for task in planned
    ]


def _build_instructions(label_schema: dict[str, Any], template_id: str | None) -> str:
    required = label_schema.get("required", list(label_schema.get("properties", {}).keys()))
    fields = ", ".join(required)
    if template_id == SUPPORT_CALL_TEMPLATE:
        return f"Label each support-call segment with: {fields}."
    if template_id == DOCUMENT_CLASSIFICATION_TEMPLATE:
        return f"Classify each document segment with: {fields}."
    return f"Label each segment with: {fields}."


def _encode_segment_payload(
    *,
    segment_ids: list[uuid.UUID],
    label_schema: dict[str, Any],
    schema_template: str | None,
) -> str:
    payload: dict[str, Any] = {
        "segment_ids": [str(segment_id) for segment_id in segment_ids],
        "label_schema": label_schema,
    }
    if schema_template:
        payload["schema_template"] = schema_template
    return json.dumps(payload)
