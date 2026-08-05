from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobStageResponse(BaseModel):
    """One pipeline stage row for SSE snapshots."""

    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_detail: str | None = None
