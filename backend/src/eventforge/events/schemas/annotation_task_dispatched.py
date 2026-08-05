from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    ANNOTATION_TASK_DISPATCHED_SCHEMA_VERSION,
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
)
from eventforge.events.schemas.envelope import EventEnvelope


class AnnotationTaskDispatchedPayload(BaseModel):
    """One parallel annotation sub-task dispatched to the annotation worker."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    task_index: int = Field(ge=0)
    instructions: str = Field(min_length=1)
    segment_ids: list[UUID] = Field(min_length=1)


class AnnotationTaskDispatchedEvent(EventEnvelope):
    """Emitted to fan out an annotation sub-task (eventforge.annotation.task.dispatched)."""

    detail_type: Literal["eventforge.annotation.task.dispatched"] = (
        DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED
    )
    schema_version: Literal["1.0"] = ANNOTATION_TASK_DISPATCHED_SCHEMA_VERSION
    payload: AnnotationTaskDispatchedPayload


def build_annotation_task_dispatched_event(
    *,
    job_id: UUID,
    correlation_id: str,
    task_id: UUID,
    task_index: int,
    instructions: str,
    segment_ids: list[UUID],
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> AnnotationTaskDispatchedEvent:
    return AnnotationTaskDispatchedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=AnnotationTaskDispatchedPayload(
            task_id=task_id,
            task_index=task_index,
            instructions=instructions,
            segment_ids=segment_ids,
        ),
    )
