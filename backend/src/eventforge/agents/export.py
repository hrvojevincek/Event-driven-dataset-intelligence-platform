"""Export stage agent — merge annotation batches into JSONL and QC report."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.otel import traced_agent
from eventforge.db.models import DatasetExport, JobStageName, JobStatus
from eventforge.db.repositories import (
    AnnotationBatchRepository,
    AssetRepository,
    DatasetExportRepository,
    ProcessedEventRepository,
    ProjectRepository,
    SegmentRepository,
)
from eventforge.db.repositories.job import JobStageRepository
from eventforge.db.repositories.llm_usage import LLMUsageRepository
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_EXPORT, EventPublisher, EventPublishError
from eventforge.events.schemas import (
    DETAIL_TYPE_EXPORT_COMPLETED,
    WORKER_NAME_EXPORT,
    AnnotationAllCompletedEvent,
    ExportCompletedEvent,
    build_export_completed_event,
)
from eventforge.events.schemas.constants import DETAIL_TYPE_ANNOTATION_ALL_COMPLETED
from eventforge.services.export import build_qc_report, merge_batches_to_jsonl


async def _load_or_create_export(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    expected_task_count: int,
) -> tuple[DatasetExport, int, int]:
    export_repo = DatasetExportRepository(session)
    existing = await export_repo.get_by_job_id(project_id)
    if existing is not None:
        batches = await AnnotationBatchRepository(session).list_by_job_id(project_id)
        segment_count = existing.export_content.count("\n") if existing.export_content else 0
        return existing, len(batches), segment_count

    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if project is None:
        msg = f"Project not found for export: {project_id}"
        raise ValueError(msg)

    batch_repo = AnnotationBatchRepository(session)
    batches = await batch_repo.list_by_job_id(project_id)
    if len(batches) < expected_task_count:
        msg = f"Export waiting for annotation batches: {len(batches)}/{expected_task_count}"
        raise ValueError(msg)

    segment_repo = SegmentRepository(session)
    segments = await segment_repo.list_by_job_id(project_id)
    assets = await AssetRepository(session).list_by_job_id(project_id)
    assets_by_id = {asset.id: asset for asset in assets}

    merge_result = merge_batches_to_jsonl(project, batches, segments, assets_by_id)
    total_cost = await LLMUsageRepository(session).total_cost_by_job_id(project_id)
    qc_report = build_qc_report(
        project=project,
        records=merge_result.records,
        total_segments=len(segments),
        batch_count=len(batches),
        total_cost_usd=total_cost,
    )

    export = DatasetExport(
        job_id=project_id,
        export_content=merge_result.jsonl,
        qc_report_json=qc_report.to_json(),
    )
    session.add(export)
    await session.flush()
    return export, len(batches), merge_result.segment_count


@traced_agent(WORKER_NAME_EXPORT)
async def process_annotation_all_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: AnnotationAllCompletedEvent,
) -> ExportCompletedEvent | None:
    """Run export after all annotation tasks finish. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_EXPORT):
        return None

    project_repo = ProjectRepository(session)
    stage_repo = JobStageRepository(session)

    project = await project_repo.get_by_id(event.job_id)
    if project is None:
        msg = f"Project not found for export: {event.job_id}"
        raise ValueError(msg)

    batch_count = await AnnotationBatchRepository(session).count_by_job_id(project.id)
    if batch_count < event.payload.task_count:
        await processed_repo.release_claim(event_id, WORKER_NAME_EXPORT)
        await session.commit()
        return None

    export_stage = await stage_repo.get_by_job_and_stage(
        project.id,
        JobStageName.EXPORT.value,
    )
    if export_stage is None:
        msg = f"Export stage missing for project: {project.id}"
        raise ValueError(msg)

    await stage_repo.mark_running(export_stage)
    export, batch_count, segment_count = await _load_or_create_export(
        session,
        project.id,
        expected_task_count=event.payload.task_count,
    )

    completed_event = build_export_completed_event(
        job_id=project.id,
        correlation_id=event.correlation_id,
        export_id=export.id,
        batch_count=batch_count,
        segment_count=segment_count or None,
        event_id=deterministic_event_id(project.id, DETAIL_TYPE_EXPORT_COMPLETED),
    )

    project.status = JobStatus.COMPLETED.value
    await stage_repo.mark_completed(export_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_EXPORT)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_EXPORT)
        await session.commit()
        raise

    return completed_event


def parse_annotation_all_completed_event(detail: dict) -> AnnotationAllCompletedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_ANNOTATION_ALL_COMPLETED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return AnnotationAllCompletedEvent.model_validate(detail)
