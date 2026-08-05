"""Submit and read dataset projects."""

import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.schemas.llm_usage import LLMUsageCallResponse, LLMUsageSummaryResponse
from eventforge.api.schemas.projects import (
    AssetResponse,
    DatasetExportSummaryResponse,
    ProjectDetailResponse,
    ProjectSummaryResponse,
    QCReportResponse,
)
from eventforge.api.schemas.stages import JobStageResponse
from eventforge.core.config import get_settings
from eventforge.core.otel import agent_span
from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    Asset,
    AssetFetchStatus,
    Job,
    JobStage,
    JobStatus,
    LLMUsage,
    StageStatus,
    User,
)
from eventforge.db.repositories import (
    AssetRepository,
    JobRepository,
    LLMUsageRepository,
    ProcessedEventRepository,
)
from eventforge.events.publisher import EVENT_SOURCE_API, PUBLISHER_WORKER_NAME, EventPublisher
from eventforge.events.schemas import build_project_submitted_event
from eventforge.services.intake import resolve_schema, validate_upload
from eventforge.services.storage.local import LocalStorage, get_local_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitProjectResult:
    """Identifiers returned after a project is submitted and persisted."""

    job_id: uuid.UUID
    correlation_id: str
    asset_count: int


@dataclass(frozen=True)
class UploadPayload:
    """One uploaded file passed from the API layer."""

    filename: str
    content: bytes


# Service (submit_project) — real work: resolve schema template, 
# create Job/stages/assets, write files to disk, publish project.submitted, commit.
async def submit_project(
    session: AsyncSession,
    publisher: EventPublisher,
    user: User,
    *,
    name: str,
    uploads: list[UploadPayload],
    schema_template: str | None = None,
    schema_json: dict | None = None,
    domain: str = "documents",
    storage: LocalStorage | None = None,
    max_upload_file_bytes: int | None = None,
    max_upload_files: int | None = None,
) -> SubmitProjectResult:
    """Persist project metadata, store uploads locally, and emit project.submitted."""
    if not uploads:
        msg = "At least one file is required"
        raise ValueError(msg)

    store = storage or get_local_storage()
    app_settings = get_settings()
    max_files = max_upload_files or app_settings.max_upload_files_per_project
    max_bytes = max_upload_file_bytes or app_settings.max_upload_file_bytes
    if len(uploads) > max_files:
        msg = f"Too many files (max {max_files})"
        raise ValueError(msg)

    resolved_schema, template_id = resolve_schema(
        schema_template=schema_template,
        schema_json=schema_json,
    )

    job_id = uuid.uuid4()
    correlation_id = uuid.uuid4().hex

    job = Job(
        id=job_id,
        user_id=user.id,
        correlation_id=correlation_id,
        name=name,
        description=None,
        schema_json=resolved_schema,
        schema_template=template_id,
        domain=domain,
        status=JobStatus.PENDING.value,
    )
    session.add(job)

    for stage_name in PIPELINE_STAGE_NAMES:
        session.add(
            JobStage(
                job_id=job_id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )

    assets: list[Asset] = []
    for upload in uploads:
        validated = validate_upload(
            upload.filename,
            upload.content,
            max_bytes=max_bytes,
        )
        _, storage_uri = store.save_bytes(job_id, validated.filename, upload.content)
        asset = Asset(
            job_id=job_id,
            filename=validated.filename,
            mime_type=validated.mime_type,
            storage_uri=storage_uri,
            byte_size=validated.byte_size,
            provenance=validated.provenance_json,
            fetch_status=AssetFetchStatus.PENDING.value,
        )
        session.add(asset)
        assets.append(asset)

    await session.flush()

    event = build_project_submitted_event(
        job_id=job_id,
        correlation_id=correlation_id,
        name=name,
        schema_json=resolved_schema,
        schema_template=template_id,
        domain=domain,
        asset_count=len(assets),
    )

    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)
    if await processed_repo.try_claim(event_id, PUBLISHER_WORKER_NAME):
        with agent_span(
            "api",
            "submit_project",
            correlation_id=correlation_id,
            job_id=str(job_id),
            event_id=event_id,
        ):
            await publisher.publish(event, source=EVENT_SOURCE_API)
    else:
        logger.info(
            "Skipped publish; project.submitted already claimed",
            extra={
                "event_id": event_id,
                "job_id": str(job_id),
                "correlation_id": correlation_id,
            },
        )

    await session.commit()
    return SubmitProjectResult(
        job_id=job_id,
        correlation_id=correlation_id,
        asset_count=len(assets),
    )


_STAGE_ORDER = {stage.value: index for index, stage in enumerate(PIPELINE_STAGE_NAMES)}


def _build_llm_usage_summary(
    records: list[LLMUsage],
    total_cost_usd: Decimal,
) -> LLMUsageSummaryResponse:
    return LLMUsageSummaryResponse(
        total_cost_usd=float(total_cost_usd),
        calls=[
            LLMUsageCallResponse(
                id=record.id,
                agent_name=record.agent_name,
                model=record.model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=float(record.cost_usd),
                created_at=record.created_at,
            )
            for record in records
        ],
    )


async def _asset_count_for_job(session: AsyncSession, job_id: uuid.UUID) -> int:
    result = await session.scalar(
        select(func.count()).select_from(Asset).where(Asset.job_id == job_id)
    )
    return int(result or 0)


def _job_to_summary_response(job: Job, asset_count: int) -> ProjectSummaryResponse:
    return ProjectSummaryResponse(
        job_id=job.id,
        correlation_id=job.correlation_id,
        name=job.name,
        schema_template=job.schema_template,
        domain=job.domain,
        status=job.status,
        asset_count=asset_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _job_to_detail_response(
    job: Job,
    *,
    assets: list[AssetResponse],
    llm_usage: LLMUsageSummaryResponse,
) -> ProjectDetailResponse:
    stages = sorted(job.stages, key=lambda stage: _STAGE_ORDER.get(stage.stage, 99))

    dataset_export: DatasetExportSummaryResponse | None = None
    if job.dataset_export is not None:
        export = job.dataset_export
        qc_data = export.qc_report_json
        line_count = sum(1 for line in export.export_content.splitlines() if line.strip())
        dataset_export = DatasetExportSummaryResponse(
            id=export.id,
            line_count=line_count,
            created_at=export.created_at,
            qc_report=QCReportResponse(
                coverage_pct=float(qc_data.get("coverage_pct", 0.0)),
                schema_compliance_pct=float(qc_data.get("schema_compliance_pct", 0.0)),
                low_confidence_segment_ids=[
                    str(segment_id) for segment_id in qc_data.get("low_confidence_segment_ids", [])
                ],
                total_cost_usd=float(qc_data.get("total_cost_usd", 0.0)),
                segment_count=int(qc_data.get("segment_count", 0)),
                labeled_count=int(qc_data.get("labeled_count", 0)),
                batch_count=int(qc_data.get("batch_count", 0)),
                flags=[str(flag) for flag in qc_data.get("flags", [])],
            ),
        )

    return ProjectDetailResponse(
        job_id=job.id,
        correlation_id=job.correlation_id,
        name=job.name,
        schema_template=job.schema_template,
        domain=job.domain,
        status=job.status,
        label_schema_json=json.dumps(job.schema_json),
        created_at=job.created_at,
        updated_at=job.updated_at,
        stages=[
            JobStageResponse(
                stage=stage.stage,
                status=stage.status,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                duration_ms=stage.duration_ms,
                error_detail=stage.error_detail,
            )
            for stage in stages
        ],
        assets=assets,
        dataset_export=dataset_export,
        llm_usage=llm_usage,
    )


async def list_projects(session: AsyncSession, user: User) -> list[ProjectSummaryResponse]:
    """Return all projects for the current user, newest first."""
    jobs = await JobRepository(session).list_by_user_id(user.id)
    summaries: list[ProjectSummaryResponse] = []
    for job in jobs:
        asset_count = await _asset_count_for_job(session, job.id)
        summaries.append(_job_to_summary_response(job, asset_count))
    return summaries


async def get_project_detail(
    session: AsyncSession,
    project_id: uuid.UUID,
    user: User,
) -> ProjectDetailResponse | None:
    """Load full project detail for the dashboard."""
    job = await JobRepository(session).get_by_id(project_id)
    if job is None or job.user_id != user.id:
        return None

    usage_repo = LLMUsageRepository(session)
    records = await usage_repo.list_by_job_id(project_id)
    total_cost = await usage_repo.total_cost_by_job_id(project_id)
    llm_usage = _build_llm_usage_summary(records, total_cost)

    asset_records = await AssetRepository(session).list_by_job_id(project_id)
    assets = [
        AssetResponse(
            id=asset.id,
            filename=asset.filename,
            mime_type=asset.mime_type,
            byte_size=asset.byte_size,
            fetch_status=asset.fetch_status,
            created_at=asset.created_at,
        )
        for asset in asset_records
    ]

    return _job_to_detail_response(job, assets=assets, llm_usage=llm_usage)


async def delete_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    user: User,
) -> bool:
    """Delete a project and its related records for the current user."""
    deleted = await JobRepository(session).delete_for_user(project_id, user.id)
    if not deleted:
        return False
    await session.commit()
    return True
