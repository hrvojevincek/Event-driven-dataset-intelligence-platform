import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_stage
from eventforge.db.models import AnnotationTask, JobStageName
from eventforge.db.repositories import (
    AnnotationTaskRepository,
    JobRepository,
    SegmentRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_PLANNING, EventPublisher
from eventforge.events.schemas import (
    DETAIL_TYPE_PLANNING_COMPLETED,
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    WORKER_NAME_PLANNING,
    PlanningCompletedEvent,
    PreprocessingCompletedEvent,
    build_planning_completed_event,
)
from eventforge.services.planning import build_annotation_tasks
from eventforge.services.planning.task_builder import persist_planned_tasks
from eventforge.stages._runtime import StageRun, parse_event


async def _load_or_create_tasks(
    session: AsyncSession,
    project_id: uuid.UUID,
    segment_ids: list[uuid.UUID],
    *,
    segments_per_task: int | None = None,
) -> list[AnnotationTask]:
    task_repo = AnnotationTaskRepository(session)
    existing = await task_repo.list_by_project_id(project_id)
    if existing:
        return existing

    project_repo = JobRepository(session)
    project = await project_repo.get_by_id(project_id)
    if project is None:
        msg = f"Project not found for planning: {project_id}"
        raise ValueError(msg)

    segment_repo = SegmentRepository(session)
    segments = await segment_repo.list_by_ids(segment_ids)
    if len(segments) != len(segment_ids):
        msg = f"Segments missing for planning project: {project_id}"
        raise ValueError(msg)

    planned = build_annotation_tasks(project, segments, segments_per_task=segments_per_task)
    tasks = await persist_planned_tasks(session, project_id, planned)
    return tasks


@traced_stage(WORKER_NAME_PLANNING)
async def process_preprocessing_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: PreprocessingCompletedEvent,
) -> PlanningCompletedEvent | None:
    """Run planning for one preprocessing.completed event. Returns None if already processed."""
    run = await StageRun.begin(
        session,
        publisher,
        event,
        worker_name=WORKER_NAME_PLANNING,
    )
    if run is None:
        return None

    planning_stage = await run.require_stage(JobStageName.PLANNING)
    settings = get_settings()
    await run.mark_running(planning_stage)
    tasks = await _load_or_create_tasks(
        session,
        run.project.id,
        event.payload.segment_ids,
        segments_per_task=settings.planning_segments_per_task,
    )

    completed_event = build_planning_completed_event(
        job_id=run.project.id,
        correlation_id=event.correlation_id,
        task_ids=[task.id for task in tasks],
        event_id=deterministic_event_id(run.project.id, DETAIL_TYPE_PLANNING_COMPLETED),
    )

    await run.complete_stage(planning_stage)
    await run.publish(completed_event, source=EVENT_SOURCE_PLANNING)
    return completed_event


def parse_preprocessing_completed_event(detail: dict) -> PreprocessingCompletedEvent:
    return parse_event(detail, DETAIL_TYPE_PREPROCESSING_COMPLETED, PreprocessingCompletedEvent)
