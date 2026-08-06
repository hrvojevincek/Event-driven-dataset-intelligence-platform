import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import JobStatus
from eventforge.db.repositories import JobRepository, JobStageRepository, ProcessedEventRepository
from eventforge.events.deterministic import deterministic_pipeline_failed_event_id
from eventforge.events.publisher import EVENT_SOURCE_DLQ, EventPublisher, EventPublishError
from eventforge.events.schemas import (
    WORKER_NAME_DLQ,
    PipelineFailedEvent,
    build_pipeline_failed_event,
)
from eventforge.events.schemas.envelope import EventEnvelope
from eventforge.events.stage_mapping import (
    source_queue_for_detail_type,
    stage_for_failed_detail_type,
)

logger = logging.getLogger(__name__)

DEFAULT_DLQ_ERROR_MESSAGE = "Message exceeded max receive count and was moved to DLQ"


def parse_failed_event_detail(detail: dict) -> EventEnvelope:
    """Parse the inbound event envelope from a redriven SQS/DLQ message body."""
    try:
        return EventEnvelope.model_validate(detail)
    except ValidationError as exc:
        msg = f"Invalid event envelope in DLQ message: {exc}"
        raise ValueError(msg) from exc


async def process_pipeline_failure(
    session: AsyncSession,
    publisher: EventPublisher,
    *,
    failed_event: EventEnvelope,
    error_message: str = DEFAULT_DLQ_ERROR_MESSAGE,
    source_queue: str | None = None,
    receive_count: int | None = None,
    claim_worker_name: str = WORKER_NAME_DLQ,
    publish_source: str = EVENT_SOURCE_DLQ,
) -> PipelineFailedEvent | None:
    """Record terminal pipeline failure and emit pipeline.failed. Returns None if duplicate."""
    processed_repo = ProcessedEventRepository(session)
    failed_event_id = str(failed_event.event_id)

    if not await processed_repo.try_claim(failed_event_id, claim_worker_name):
        return None

    stage = stage_for_failed_detail_type(failed_event.detail_type)
    if stage is None:
        await processed_repo.release_claim(failed_event_id, claim_worker_name)
        msg = f"Unknown detail_type for pipeline failure: {failed_event.detail_type}"
        raise ValueError(msg)

    if source_queue is None:
        source_queue = source_queue_for_detail_type(failed_event.detail_type)

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)

    job = await job_repo.get_by_id(failed_event.job_id)
    if job is None:
        await processed_repo.release_claim(failed_event_id, claim_worker_name)
        msg = f"Job not found for pipeline failure: {failed_event.job_id}"
        raise ValueError(msg)

    job_stage = await stage_repo.get_by_job_and_stage(job.id, stage)
    if job_stage is None:
        await processed_repo.release_claim(failed_event_id, claim_worker_name)
        msg = f"Stage {stage} missing for failed job: {job.id}"
        raise ValueError(msg)

    if job.status != JobStatus.FAILED.value:
        await stage_repo.mark_failed(job_stage, error_message)
        job.status = JobStatus.FAILED.value

    pipeline_failed = build_pipeline_failed_event(
        job_id=job.id, correlation_id=failed_event.correlation_id, stage=stage,
        failed_event_id=failed_event.event_id,
        failed_detail_type=failed_event.detail_type,
        error_message=error_message, source_queue=source_queue,
        receive_count=receive_count,
        event_id=deterministic_pipeline_failed_event_id(
            job.id, failed_event.event_id),)

    await session.commit()

    try:
        await publisher.publish(pipeline_failed, source=publish_source)
    except EventPublishError:
        await processed_repo.release_claim(failed_event_id, claim_worker_name)
        await session.commit()
        raise

    return pipeline_failed
