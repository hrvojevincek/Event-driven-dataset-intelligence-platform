import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.agents.planning import (
    parse_preprocessing_completed_event,
    process_preprocessing_completed,
)
from eventforge.db.models import (
    AnnotationTask,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    Segment,
    StageStatus,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    DETAIL_TYPE_PLANNING_COMPLETED,
    WORKER_NAME_PLANNING,
    build_planning_completed_event,
    build_preprocessing_completed_event,
)
from eventforge.services.intake.templates import SUPPORT_CALL_TEMPLATE
from eventforge.workers.planning import PlanningWorker


async def _seed_project_with_segments(
    db_session: AsyncSession,
) -> tuple[Job, JobStage, list[Segment]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"planning-{suffix}@example.com", auth_subject_id=f"planning-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-planning-{suffix}",
        name="Support calls batch",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=json.dumps(
            {
                "type": "object",
                "properties": {
                    "emotion": {"type": "string"},
                    "intent": {"type": "string"},
                    "topic": {"type": "string"},
                    "resolution_status": {"type": "string"},
                },
                "required": ["emotion", "intent", "topic", "resolution_status"],
            }
        ),
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    stage = JobStage(
        job_id=job.id,
        stage=JobStageName.PLANNING.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(stage)

    asset_id = uuid.uuid4()
    segments = [
        Segment(
            job_id=job.id,
            asset_id=asset_id,
            segment_index=index,
            content=f"Customer utterance {index}",
        )
        for index in range(3)
    ]
    db_session.add_all(segments)
    await db_session.flush()
    return job, stage, segments


def test_parse_preprocessing_completed_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_preprocessing_completed_event({"detail_type": "eventforge.intake.completed"})


async def test_process_preprocessing_completed_writes_tasks_and_updates_stage(
    db_session: AsyncSession,
) -> None:
    job, stage, segments = await _seed_project_with_segments(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_preprocessing_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        segment_ids=[segment.id for segment in segments],
    )

    result = await process_preprocessing_completed(db_session, mock_publisher, inbound)

    assert result is not None
    assert result.detail_type == DETAIL_TYPE_PLANNING_COMPLETED
    assert result.payload.task_count == len(segments)
    mock_publisher.publish.assert_awaited_once()

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value

    task_count = await db_session.scalar(
        select(func.count()).select_from(AnnotationTask).where(AnnotationTask.job_id == job.id)
    )
    assert task_count == len(segments)

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_PLANNING


async def test_process_preprocessing_completed_skips_duplicate_event(
    db_session: AsyncSession,
) -> None:
    job, _, segments = await _seed_project_with_segments(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_preprocessing_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        segment_ids=[segment.id for segment in segments],
    )

    await process_preprocessing_completed(db_session, mock_publisher, inbound)
    mock_publisher.reset_mock()

    duplicate = await process_preprocessing_completed(db_session, mock_publisher, inbound)
    assert duplicate is None
    mock_publisher.publish.assert_not_awaited()


async def test_planning_worker_deletes_message_on_success() -> None:
    worker = PlanningWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_preprocessing_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        segment_ids=[UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")],
    )
    body = json.dumps({"detail": json.loads(event.model_dump_json())})
    mock_client.receive_message.return_value = {
        "Messages": [{"ReceiptHandle": "rh-1", "Body": body, "MessageId": "m-1"}]
    }
    worker._client = mock_client
    worker._queue_url = "http://localstack/000000000000/eventforge-knowledge-mining"

    with patch.object(worker, "handle_message", new=AsyncMock()):
        handled = await worker.poll_once()

    assert handled == 1
    worker._delete_message.assert_called_once_with("rh-1")


def test_build_planning_completed_event_sets_payload() -> None:
    task_ids = [
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    event = build_planning_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-out",
        task_ids=task_ids,
    )
    assert event.detail_type == DETAIL_TYPE_PLANNING_COMPLETED
    assert event.payload.task_count == 2
    assert event.payload.task_ids == task_ids
