from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    ANNOTATION_ALL_COMPLETED_SCHEMA_VERSION,
    DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
)
from eventforge.events.schemas.envelope import EventEnvelope


class AnnotationAllCompletedPayload(BaseModel):
    """Summary emitted after all annotation sub-tasks finish."""

    model_config = ConfigDict(extra="forbid")

    task_count: int = Field(ge=1)


class AnnotationAllCompletedEvent(EventEnvelope):
    """Emitted when all annotation sub-tasks finish (eventforge.annotation.all_completed)."""

    detail_type: Literal["eventforge.annotation.all_completed"] = (
        DETAIL_TYPE_ANNOTATION_ALL_COMPLETED
    )
    schema_version: Literal["1.0"] = ANNOTATION_ALL_COMPLETED_SCHEMA_VERSION
    payload: AnnotationAllCompletedPayload


def build_annotation_all_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    task_count: int,
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> AnnotationAllCompletedEvent:
    return AnnotationAllCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=AnnotationAllCompletedPayload(task_count=task_count),
    )
