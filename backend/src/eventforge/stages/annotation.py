"""Annotation stage — fan-out from planning.completed and label tasks."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_stage
from eventforge.db.models import AnnotationBatch, AnnotationTask, JobStageName
from eventforge.db.repositories import (
    AnnotationBatchRepository,
    AnnotationTaskRepository,
    SegmentRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_ANNOTATION, EventPublisher
from eventforge.events.schemas import (
    DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
    DETAIL_TYPE_PLANNING_COMPLETED,
    WORKER_NAME_ANNOTATION,
    WORKER_NAME_ANNOTATION_ORCHESTRATOR,
    AnnotationAllCompletedEvent,
    AnnotationTaskCompletedEvent,
    AnnotationTaskDispatchedEvent,
    PlanningCompletedEvent,
    build_annotation_all_completed_event,
    build_annotation_task_completed_event,
    build_annotation_task_dispatched_event,
)
from eventforge.services.annotation import label_segments
from eventforge.services.llm.client import LLMClient, get_llm_client
from eventforge.services.planning.schema_templates import load_label_schema
from eventforge.stages._runtime import StageRun, parse_event


def _segment_ids_for_task(task: AnnotationTask) -> list[uuid.UUID]:
    return task.segment_ids


async def _build_dispatched_events(
    event: PlanningCompletedEvent,
    tasks: list[AnnotationTask],
) -> list[AnnotationTaskDispatchedEvent]:
    by_id = {task.id: task for task in tasks}
    dispatched: list[AnnotationTaskDispatchedEvent] = []
    for task_id in event.payload.task_ids:
        task = by_id.get(task_id)
        if task is None:
            msg = f"Annotation task missing for planning fan-out: {task_id}"
            raise ValueError(msg)
        dispatched.append(
            build_annotation_task_dispatched_event(
                job_id=event.job_id,
                correlation_id=event.correlation_id,
                task_id=task.id,
                task_index=task.task_index,
                instructions=task.instructions,
                segment_ids=_segment_ids_for_task(task),
                event_id=deterministic_event_id(
                    event.job_id,
                    f"{DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED}:{task.task_index}",
                ),
            )
        )
    return dispatched


async def _load_or_create_batch(
    session: AsyncSession,
    event: AnnotationTaskDispatchedEvent,
    *,
    llm_client: LLMClient,
    label_schema: dict,
) -> AnnotationBatch:
    batch_repo = AnnotationBatchRepository(session)
    existing = await batch_repo.get_by_task_id(event.payload.task_id)
    if existing is not None:
        return existing

    task_repo = AnnotationTaskRepository(session)
    tasks = await task_repo.list_by_ids([event.payload.task_id])
    if not tasks:
        msg = f"Annotation task not found: {event.payload.task_id}"
        raise ValueError(msg)

    segment_repo = SegmentRepository(session)
    segments = await segment_repo.list_by_ids(event.payload.segment_ids)
    if len(segments) != len(event.payload.segment_ids):
        msg = f"Segments missing for annotation task: {event.payload.task_id}"
        raise ValueError(msg)

    # Preserve dispatch order
    by_id = {segment.id: segment for segment in segments}
    ordered = [by_id[segment_id] for segment_id in event.payload.segment_ids]

    labeled = await label_segments(
        llm_client,
        project_id=event.job_id,
        instructions=event.payload.instructions,
        segments=ordered,
        label_schema=label_schema,
    )

    batch = AnnotationBatch(
        job_id=event.job_id,
        task_id=event.payload.task_id,
        task_index=event.payload.task_index,
        labels_json=labeled.labels_json,
        segment_count=len(ordered),
        confidence=labeled.confidence,
    )
    session.add(batch)
    await session.flush()
    return batch


@traced_stage(WORKER_NAME_ANNOTATION_ORCHESTRATOR)
async def prepare_annotation_fanout(
    session: AsyncSession,
    event: PlanningCompletedEvent,
) -> list[AnnotationTaskDispatchedEvent] | None:
    """Build annotation sub-tasks from planning.completed without publishing events."""
    run = await StageRun.begin(
        session,
        None,
        event,
        worker_name=WORKER_NAME_ANNOTATION_ORCHESTRATOR,
    )
    if run is None:
        return None

    annotation_stage = await run.require_stage(JobStageName.ANNOTATION)
    tasks = await AnnotationTaskRepository(session).list_by_ids(event.payload.task_ids)
    if len(tasks) != len(event.payload.task_ids):
        msg = f"Annotation tasks missing for project: {event.job_id}"
        raise ValueError(msg)

    await run.mark_running(annotation_stage)
    dispatched_events = await _build_dispatched_events(event, tasks)
    await run.commit()
    return dispatched_events


@traced_stage(WORKER_NAME_ANNOTATION_ORCHESTRATOR)
async def process_planning_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: PlanningCompletedEvent,
) -> list[AnnotationTaskDispatchedEvent] | None:
    """Fan out annotation sub-tasks from planning.completed. Returns None if already processed."""
    dispatched_events = await prepare_annotation_fanout(session, event)
    if dispatched_events is None:
        return None

    run = await StageRun.wrap_claimed(
        session,
        publisher,
        event,
        worker_name=WORKER_NAME_ANNOTATION_ORCHESTRATOR,
    )
    await run.publish_many(dispatched_events, source=EVENT_SOURCE_ANNOTATION)
    return dispatched_events


@traced_stage(WORKER_NAME_ANNOTATION)
async def process_annotation_task_dispatched(
    session: AsyncSession,
    publisher: EventPublisher,
    event: AnnotationTaskDispatchedEvent,
    *,
    llm_client: LLMClient | None = None,
    step_functions_task_token: str | None = None,
) -> AnnotationTaskCompletedEvent | None:
    """Run one annotation sub-task. Returns None if already processed."""
    run = await StageRun.begin(
        session,
        publisher,
        event,
        worker_name=WORKER_NAME_ANNOTATION,
    )
    if run is None:
        return None

    await run.require_stage(JobStageName.ANNOTATION)
    label_schema = load_label_schema(run.project.schema_json, run.project.schema_template)
    llm_client = llm_client or get_llm_client(session=session)
    batch = await _load_or_create_batch(
        session,
        event,
        llm_client=llm_client,
        label_schema=label_schema,
    )

    completed_event = build_annotation_task_completed_event(
        job_id=run.project.id,
        correlation_id=event.correlation_id,
        task_id=event.payload.task_id,
        batch_id=batch.id,
        task_index=event.payload.task_index,
        event_id=deterministic_event_id(
            run.project.id,
            f"{DETAIL_TYPE_ANNOTATION_TASK_COMPLETED}:{event.payload.task_index}",
        ),
    )

    task_repo = AnnotationTaskRepository(session)
    batch_repo = AnnotationBatchRepository(session)
    expected_tasks = len(await task_repo.list_by_project_id(run.project.id))
    batch_count = await batch_repo.count_by_job_id(run.project.id)
    all_completed_event: AnnotationAllCompletedEvent | None = None
    if batch_count >= expected_tasks:
        annotation_stage = await run.require_stage(JobStageName.ANNOTATION)
        await run.mark_completed(annotation_stage)
        # Step Functions publishes annotation.all_completed after Map; local mode emits here.
        if get_settings().research_orchestration_mode == "local":
            all_completed_event = build_annotation_all_completed_event(
                job_id=run.project.id,
                correlation_id=event.correlation_id,
                task_count=expected_tasks,
                event_id=deterministic_event_id(
                    run.project.id,
                    DETAIL_TYPE_ANNOTATION_ALL_COMPLETED,
                ),
            )

    await run.commit()

    await run.publish(completed_event, source=EVENT_SOURCE_ANNOTATION)
    if all_completed_event is not None:
        await run.publish(all_completed_event, source=EVENT_SOURCE_ANNOTATION)

    if step_functions_task_token:
        from eventforge.services.step_functions import send_task_success

        send_task_success(
            step_functions_task_token,
            completed_event.model_dump(mode="json"),
        )

    return completed_event


def parse_planning_completed_event(detail: dict) -> PlanningCompletedEvent:
    return parse_event(detail, DETAIL_TYPE_PLANNING_COMPLETED, PlanningCompletedEvent)


def parse_annotation_task_dispatched_event(
    detail: dict,
) -> AnnotationTaskDispatchedEvent:
    return parse_event(
        detail,
        DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
        AnnotationTaskDispatchedEvent,
    )
