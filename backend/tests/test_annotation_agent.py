import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import (
    AnnotationBatch,
    AnnotationTask,
    Asset,
    AssetFetchStatus,
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
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
    WORKER_NAME_ANNOTATION,
    WORKER_NAME_ANNOTATION_ORCHESTRATOR,
    build_annotation_task_dispatched_event,
    build_planning_completed_event,
)
from eventforge.services.intake.templates import SUPPORT_CALL_TEMPLATE
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult
from eventforge.services.planning import build_annotation_tasks
from eventforge.services.planning.task_builder import persist_planned_tasks
from eventforge.stages.annotation import (
    parse_annotation_task_dispatched_event,
    parse_planning_completed_event,
    process_annotation_task_dispatched,
    process_planning_completed,
)
from eventforge.workers.annotation import AnnotationWorker


async def _seed_project_with_tasks(
    db_session: AsyncSession,
) -> tuple[Job, JobStage, list[AnnotationTask], list[Segment]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"annotation-{suffix}@example.com",
        auth_subject_id=f"annotation-user-{suffix}",
    )
    db_session.add(user)
    await db_session.flush()

    schema = {
        "type": "object",
        "properties": {
            "emotion": {"type": "string"},
            "intent": {"type": "string"},
            "topic": {"type": "string"},
            "resolution_status": {"type": "string"},
        },
        "required": ["emotion", "intent", "topic", "resolution_status"],
    }
    job = Job(
        user_id=user.id,
        correlation_id=f"corr-annotation-{suffix}",
        name="Support calls batch",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=schema,
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    stage = JobStage(
        job_id=job.id,
        stage=JobStageName.ANNOTATION.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(stage)

    asset = Asset(
        job_id=job.id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///tmp/call_001.txt",
        byte_size=128,
        fetch_status=AssetFetchStatus.OK.value,
    )
    db_session.add(asset)
    await db_session.flush()

    segments = [
        Segment(
            job_id=job.id,
            asset_id=asset.id,
            segment_index=index,
            content=f"Customer utterance {index}",
        )
        for index in range(2)
    ]
    db_session.add_all(segments)
    await db_session.flush()

    planned = build_annotation_tasks(job, segments)
    tasks = await persist_planned_tasks(db_session, job.id, planned)
    return job, stage, tasks, segments


def _mock_llm_client() -> LLMClient:
    client = AsyncMock(spec=LLMClient)

    async def _complete(messages: list[object], **kwargs: object) -> LLMCompletionResult:
        return LLMCompletionResult(
            content=json.dumps(
                {
                    "segments": [
                        {
                            "segment_index": 0,
                            "labels": {
                                "emotion": "frustrated",
                                "intent": "complaint",
                                "topic": "billing",
                                "resolution_status": "unresolved",
                            },
                            "confidence": 0.9,
                        }
                    ]
                }
            ),
            model="gpt-4o-mini",
            input_tokens=20,
            output_tokens=40,
            cost_usd=Decimal("0.002"),
        )

    client.complete = AsyncMock(side_effect=_complete)
    return client


def test_parse_planning_completed_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_planning_completed_event({"detail_type": "eventforge.intake.completed"})


def test_parse_annotation_task_dispatched_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_annotation_task_dispatched_event(
            {"detail_type": "eventforge.planning.completed"}
        )


async def test_process_planning_completed_dispatches_tasks(
    db_session: AsyncSession,
) -> None:
    job, stage, tasks, _ = await _seed_project_with_tasks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_planning_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_ids=[task.id for task in tasks],
    )

    result = await process_planning_completed(db_session, mock_publisher, inbound)

    assert result is not None
    assert len(result) == len(tasks)
    assert all(event.detail_type == DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED for event in result)
    assert mock_publisher.publish.await_count == len(tasks)

    await db_session.refresh(stage)
    assert stage.status == StageStatus.RUNNING.value

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_ANNOTATION_ORCHESTRATOR


async def test_process_planning_completed_skips_duplicate(
    db_session: AsyncSession,
) -> None:
    job, _, tasks, _ = await _seed_project_with_tasks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_planning_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_ids=[task.id for task in tasks],
    )

    await process_planning_completed(db_session, mock_publisher, inbound)
    mock_publisher.reset_mock()

    duplicate = await process_planning_completed(db_session, mock_publisher, inbound)
    assert duplicate is None
    mock_publisher.publish.assert_not_awaited()


async def test_process_annotation_task_writes_batch_and_completes_stage(
    db_session: AsyncSession,
) -> None:
    job, stage, tasks, segments = await _seed_project_with_tasks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    llm = _mock_llm_client()

    # Fan-out claim first so stage is running
    planning_event = build_planning_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_ids=[task.id for task in tasks],
    )
    dispatched = await process_planning_completed(db_session, mock_publisher, planning_event)
    assert dispatched is not None
    mock_publisher.reset_mock()

    for event in dispatched:
        # Multi-segment batches need matching LLM response shape — force 1 segment per call
        # by using the dispatched event as-is (support-call = 1 segment/task).
        result = await process_annotation_task_dispatched(
            db_session,
            mock_publisher,
            event,
            llm_client=llm,
        )
        assert result is not None
        assert result.detail_type == DETAIL_TYPE_ANNOTATION_TASK_COMPLETED

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value

    batch_count = await db_session.scalar(
        select(func.count())
        .select_from(AnnotationBatch)
        .where(AnnotationBatch.job_id == job.id)
    )
    assert batch_count == len(tasks)

    # task.completed + all_completed on the last task
    assert mock_publisher.publish.await_count == len(tasks) + 1

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(dispatched[0].event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_ANNOTATION

    # Sanity: segment content was available
    assert segments[0].content.startswith("Customer")


async def test_process_annotation_task_skips_duplicate(
    db_session: AsyncSession,
) -> None:
    job, _, tasks, _ = await _seed_project_with_tasks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    llm = _mock_llm_client()

    planning_event = build_planning_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_ids=[task.id for task in tasks],
    )
    dispatched = await process_planning_completed(db_session, mock_publisher, planning_event)
    assert dispatched is not None
    mock_publisher.reset_mock()

    first = await process_annotation_task_dispatched(
        db_session, mock_publisher, dispatched[0], llm_client=llm
    )
    assert first is not None
    mock_publisher.reset_mock()

    duplicate = await process_annotation_task_dispatched(
        db_session, mock_publisher, dispatched[0], llm_client=llm
    )
    assert duplicate is None
    mock_publisher.publish.assert_not_awaited()


async def test_annotation_worker_deletes_message_on_success() -> None:
    worker = AnnotationWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_annotation_task_dispatched_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        task_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        task_index=0,
        instructions="Label segments",
        segment_ids=[UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")],
    )
    body = json.dumps({"detail": json.loads(event.model_dump_json())})
    mock_client.receive_message.return_value = {
        "Messages": [{"ReceiptHandle": "rh-1", "Body": body, "MessageId": "m-1"}]
    }
    worker._client = mock_client
    worker._queue_url = "http://localstack/000000000000/eventforge-research"

    with patch.object(worker, "handle_message", new=AsyncMock()):
        handled = await worker.poll_once()

    assert handled == 1
    worker._delete_message.assert_called_once_with("rh-1")
