import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_agent
from eventforge.db.models import AnnotationTask, JobStageName
from eventforge.db.repositories import (
    AnnotationTaskRepository,
    JobRepository,
    JobStageRepository,
    ProcessedEventRepository,
    SegmentRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_PLANNING, EventPublisher, EventPublishError
from eventforge.events.schemas import (
    DETAIL_TYPE_PLANNING_COMPLETED,
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    WORKER_NAME_PLANNING,
    PlanningCompletedEvent,
    PreprocessingCompletedEvent,
    build_planning_completed_event,
)
from eventforge.services.planning import build_annotation_tasks
from eventforge.services.planning.task_builder import annotation_tasks_from_planned


async def _load_or_create_tasks(
    session: AsyncSession,
    job_id: uuid.UUID,
    segment_ids: list[uuid.UUID],
    *,
    segments_per_task: int | None = None,
) -> list[AnnotationTask]:
    task_repo = AnnotationTaskRepository(session)
    existing = await task_repo.list_by_job_id(job_id)
    if existing:
        return existing

    job_repo = JobRepository(session)
    job = await job_repo.get_by_id(job_id)
    if job is None:
        msg = f"Job not found for planning: {job_id}"
        raise ValueError(msg)

    segment_repo = SegmentRepository(session)
    segments = await segment_repo.list_by_ids(segment_ids)
    if len(segments) != len(segment_ids):
        msg = f"Segments missing for planning job: {job_id}"
        raise ValueError(msg)

    planned = build_annotation_tasks(job, segments, segments_per_task=segments_per_task)
    tasks = annotation_tasks_from_planned(job_id, planned)
    session.add_all(tasks)
    await session.flush()
    return tasks


@traced_agent(WORKER_NAME_PLANNING)
async def process_preprocessing_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: PreprocessingCompletedEvent,
) -> PlanningCompletedEvent | None:
    """Run planning for one preprocessing.completed event. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_PLANNING):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for planning: {event.job_id}"
        raise ValueError(msg)

    planning_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.PLANNING.value)
    if planning_stage is None:
        msg = f"Planning stage missing for job: {job.id}"
        raise ValueError(msg)

    settings = get_settings()
    await stage_repo.mark_running(planning_stage)
    tasks = await _load_or_create_tasks(
        session,
        job.id,
        event.payload.segment_ids,
        segments_per_task=settings.planning_segments_per_task,
    )

    completed_event = build_planning_completed_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        task_ids=[task.id for task in tasks],
        event_id=deterministic_event_id(job.id, DETAIL_TYPE_PLANNING_COMPLETED),
    )

    await stage_repo.mark_completed(planning_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_PLANNING)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_PLANNING)
        await session.commit()
        raise

    return completed_event


def parse_preprocessing_completed_event(detail: dict) -> PreprocessingCompletedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_PREPROCESSING_COMPLETED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return PreprocessingCompletedEvent.model_validate(detail)
