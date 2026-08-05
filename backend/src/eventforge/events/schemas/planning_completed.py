from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    DETAIL_TYPE_PLANNING_COMPLETED,
    PLANNING_COMPLETED_SCHEMA_VERSION,
)
from eventforge.events.schemas.envelope import EventEnvelope


class PlanningCompletedPayload(BaseModel):
    """Annotation task IDs produced by the planning stage."""

    model_config = ConfigDict(extra="forbid")

    task_ids: list[UUID] = Field(min_length=1)
    task_count: int = Field(ge=1)


class PlanningCompletedEvent(EventEnvelope):
    """Emitted after annotation tasks are planned (eventforge.planning.completed)."""

    detail_type: Literal["eventforge.planning.completed"] = DETAIL_TYPE_PLANNING_COMPLETED
    schema_version: Literal["1.0"] = PLANNING_COMPLETED_SCHEMA_VERSION
    payload: PlanningCompletedPayload


def build_planning_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    task_ids: list[UUID],
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> PlanningCompletedEvent:
    return PlanningCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=PlanningCompletedPayload(
            task_ids=task_ids,
            task_count=len(task_ids),
        ),
    )
