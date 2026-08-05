from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    PREPROCESSING_COMPLETED_SCHEMA_VERSION,
)
from eventforge.events.schemas.envelope import EventEnvelope


class PreprocessingCompletedPayload(BaseModel):
    """Segment IDs produced by the preprocessing stage."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[UUID] = Field(min_length=1)
    segment_count: int = Field(ge=1)


class PreprocessingCompletedEvent(EventEnvelope):
    """Emitted after segments are extracted (eventforge.preprocessing.completed)."""

    detail_type: Literal["eventforge.preprocessing.completed"] = (
        DETAIL_TYPE_PREPROCESSING_COMPLETED
    )
    schema_version: Literal["1.0"] = PREPROCESSING_COMPLETED_SCHEMA_VERSION
    payload: PreprocessingCompletedPayload


def build_preprocessing_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    segment_ids: list[UUID],
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> PreprocessingCompletedEvent:
    return PreprocessingCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=PreprocessingCompletedPayload(
            segment_ids=segment_ids,
            segment_count=len(segment_ids),
        ),
    )
