from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eventforge.api.schemas.llm_usage import LLMUsageSummaryResponse
from eventforge.api.schemas.stages import JobStageResponse


class SubmitProjectResponse(BaseModel):
    """Response after a project is accepted and queued for intake."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    correlation_id: str
    asset_count: int = Field(ge=1)


class ProjectSummaryResponse(BaseModel):
    """Lightweight project summary for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    correlation_id: str
    name: str
    schema_template: str | None
    domain: str
    status: str
    asset_count: int
    created_at: datetime
    updated_at: datetime


class AssetResponse(BaseModel):
    """Uploaded file registered during intake."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str
    byte_size: int | None
    fetch_status: str
    created_at: datetime


class QCReportResponse(BaseModel):
    """Quality-control summary for a completed export."""

    coverage_pct: float
    schema_compliance_pct: float
    low_confidence_segment_ids: list[str]
    total_cost_usd: float
    segment_count: int
    labeled_count: int
    batch_count: int
    flags: list[str]


class DatasetExportSummaryResponse(BaseModel):
    """Export metadata without the full JSONL payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_count: int
    created_at: datetime
    qc_report: QCReportResponse


class ProjectDetailResponse(BaseModel):
    """Full project detail including stages, assets, and optional export."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    correlation_id: str
    name: str
    schema_template: str | None
    domain: str
    status: str
    label_schema_json: str
    created_at: datetime
    updated_at: datetime
    stages: list[JobStageResponse]
    assets: list[AssetResponse] = Field(default_factory=list)
    dataset_export: DatasetExportSummaryResponse | None = None
    llm_usage: LLMUsageSummaryResponse
