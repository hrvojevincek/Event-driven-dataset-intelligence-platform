"""Build annotation tasks from preprocessed segments and project schema."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import AnnotationTask, AnnotationTaskSegment, Job, Segment
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


def build_annotation_tasks(
    project: Job,
    segments: list[Segment],
    *,
    segments_per_task: int | None = None,
) -> list[PlannedTask]:
    """Batch ordered segments into annotation tasks for the project's label schema."""
    if not segments:
        msg = "At least one segment is required to plan annotation tasks"
        raise ValueError(msg)

    label_schema = load_label_schema(project.schema_json, project.schema_template)
    batch_size = segments_per_task or segments_per_task_for_template(project.schema_template)
    if batch_size < 1:
        msg = "segments_per_task must be >= 1"
        raise ValueError(msg)

    instructions = _build_instructions(label_schema, project.schema_template)
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
            )
        )
    return planned


async def persist_planned_tasks(
    session: AsyncSession,
    project_id: uuid.UUID,
    planned: list[PlannedTask],
) -> list[AnnotationTask]:
    """Materialize annotation tasks and ordered segment links."""
    tasks = [
        AnnotationTask(
            job_id=project_id,
            task_index=task.task_index,
            instructions=task.instructions,
        )
        for task in planned
    ]
    session.add_all(tasks)
    await session.flush()

    for task, plan in zip(tasks, planned, strict=True):
        for position, segment_id in enumerate(plan.segment_ids):
            session.add(
                AnnotationTaskSegment(
                    task_id=task.id,
                    segment_id=segment_id,
                    position=position,
                )
            )
    await session.flush()
    return tasks

def _build_instructions(label_schema: dict[str, Any], template_id: str | None) -> str:
    required = label_schema.get("required", list(label_schema.get("properties", {}).keys()))
    fields = ", ".join(required)
    if template_id == SUPPORT_CALL_TEMPLATE:
        return f"Label each support-call segment with: {fields}."
    if template_id == DOCUMENT_CLASSIFICATION_TEMPLATE:
        return f"Classify each document segment with: {fields}."
    return f"Label each segment with: {fields}."
