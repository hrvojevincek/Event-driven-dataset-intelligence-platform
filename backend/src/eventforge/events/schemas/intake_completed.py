from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    DETAIL_TYPE_INTAKE_COMPLETED,
    INTAKE_COMPLETED_SCHEMA_VERSION,
)
from eventforge.events.schemas.envelope import EventEnvelope


class IntakeCompletedPayload(BaseModel):
    """Asset IDs produced by the intake stage."""

    model_config = ConfigDict(extra="forbid")

    asset_ids: list[UUID] = Field(min_length=1)
    asset_count: int = Field(ge=1)


class IntakeCompletedEvent(EventEnvelope):
    """Emitted after assets are stored (eventforge.intake.completed)."""

    detail_type: Literal["eventforge.intake.completed"] = DETAIL_TYPE_INTAKE_COMPLETED
    schema_version: Literal["1.0"] = INTAKE_COMPLETED_SCHEMA_VERSION
    payload: IntakeCompletedPayload


def build_intake_completed_event(
    *,
    job_id: UUID,
    correlation_id: str,
    asset_ids: list[UUID],
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> IntakeCompletedEvent:
    return IntakeCompletedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=IntakeCompletedPayload(
            asset_ids=asset_ids,
            asset_count=len(asset_ids),
        ),
    )
