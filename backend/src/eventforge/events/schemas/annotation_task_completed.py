from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    ANNOTATION_TASK_COMPLETED_SCHEMA_VERSION,
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
)
from eventforge.events.schemas.envelope import EventEnvelope


class AnnotationTaskCompletedPayload(BaseModel):
    """Result of one completed annotation sub-task."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    batch_id: UUID
    task_index: int = Field(ge=0)


class AnnotationTaskCompletedEvent(EventEnvelope):
    """Emitted when an annotation sub-task finishes (eventforge.annotation.task.completed)."""

    detail_type: Literal["eventforge.annotation.task.completed"] = (
        DETAIL_TYPE_ANNOTATION_TASK_COMPLETED
    )
    schema_version: Literal["1.0"] = ANNOTATION_TASK_COMPLETED_SCHEMA_VERSION
    payload: AnnotationTaskCompletedPayload


def build_annotation_task_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    task_id: UUID,
    batch_id: UUID,
    task_index: int,
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> AnnotationTaskCompletedEvent:
    return AnnotationTaskCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=AnnotationTaskCompletedPayload(
            task_id=task_id,
            batch_id=batch_id,
            task_index=task_index,
        ),
    )
