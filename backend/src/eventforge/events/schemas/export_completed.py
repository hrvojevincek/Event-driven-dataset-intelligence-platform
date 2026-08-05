from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    DETAIL_TYPE_EXPORT_COMPLETED,
    EXPORT_COMPLETED_SCHEMA_VERSION,
)
from eventforge.events.schemas.envelope import EventEnvelope


class ExportCompletedPayload(BaseModel):
    """Export ID and batch count from the export stage."""

    model_config = ConfigDict(extra="forbid")

    export_id: UUID
    batch_count: int = Field(ge=1)
    segment_count: int | None = Field(default=None, ge=1)


class ExportCompletedEvent(EventEnvelope):
    """Emitted when the JSONL export is ready (eventforge.export.completed)."""

    detail_type: Literal["eventforge.export.completed"] = DETAIL_TYPE_EXPORT_COMPLETED
    schema_version: Literal["1.0"] = EXPORT_COMPLETED_SCHEMA_VERSION
    payload: ExportCompletedPayload


def build_export_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    export_id: UUID,
    batch_count: int,
    segment_count: int | None = None,
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> ExportCompletedEvent:
    return ExportCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=ExportCompletedPayload(
            export_id=export_id,
            batch_count=batch_count,
            segment_count=segment_count,
        ),
    )
