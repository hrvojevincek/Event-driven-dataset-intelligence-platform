from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from eventforge.events.schemas.constants import (
    DETAIL_TYPE_PROJECT_SUBMITTED,
    PROJECT_SUBMITTED_SCHEMA_VERSION,
)
from eventforge.events.schemas.envelope import EventEnvelope


class ProjectSubmittedPayload(BaseModel):
    """Business data for the first pipeline stage — mirrors project name, schema, and domain."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1)
    output_schema: dict[str, Any] = Field(..., alias="schema_json")
    schema_template: str | None = Field(default=None, max_length=64)
    domain: str = Field(default="documents", max_length=32)
    asset_count: int | None = Field(default=None, ge=0)


class ProjectSubmittedEvent(EventEnvelope):
    """Emitted when the API accepts a new dataset project (eventforge.project.submitted)."""

    detail_type: Literal["eventforge.project.submitted"] = DETAIL_TYPE_PROJECT_SUBMITTED
    schema_version: Literal["1.0"] = PROJECT_SUBMITTED_SCHEMA_VERSION
    payload: ProjectSubmittedPayload


def build_project_submitted_event(
    *,
    job_id: UUID,
    correlation_id: str,
    name: str,
    schema_json: dict[str, Any],
    schema_template: str | None = None,
    domain: str = "documents",
    asset_count: int | None = None,
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
) -> ProjectSubmittedEvent:
    """Factory for the API publisher — fills envelope + payload in one call."""
    return ProjectSubmittedEvent(
        event_id=event_id or uuid4(),
        correlation_id=correlation_id,
        job_id=job_id,
        timestamp=timestamp or datetime.now(tz=UTC),
        payload=ProjectSubmittedPayload(
            name=name,
            output_schema=schema_json,
            schema_template=schema_template,
            domain=domain,
            asset_count=asset_count,
        ),
    )
