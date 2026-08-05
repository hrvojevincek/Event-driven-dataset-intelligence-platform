from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubmitProjectResponse(BaseModel):
    """Response after a project is accepted and queued for intake."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    correlation_id: str
    asset_count: int = Field(ge=1)
