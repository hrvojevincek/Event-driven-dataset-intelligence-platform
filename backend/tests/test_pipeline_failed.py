import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.core.config import get_settings
from eventforge.db.models import Job, JobStage, JobStageName, JobStatus, StageStatus, User
from eventforge.db.repositories import JobStageRepository
from eventforge.db.session import reset_engine
from eventforge.events.deterministic import deterministic_pipeline_failed_event_id
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher, EventPublishError
from eventforge.events.schemas import (
    DETAIL_TYPE_PIPELINE_FAILED,
    build_project_submitted_event,
)
from eventforge.events.stage_mapping import stage_for_failed_detail_type
from eventforge.services.pipeline_failure import (
    parse_failed_event_detail,
    process_pipeline_failure,
)
from eventforge.workers.dlq import DlqWorker

settings = get_settings()


@pytest.fixture
async def db_session() -> AsyncSession:
    reset_engine()
    engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
    reset_engine()


async def _seed_job_with_stages(db_session: AsyncSession) -> Job:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"fail-{suffix}@example.com", auth_subject_id=f"fail-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-fail-{suffix}",
        name="Pipeline failure test",
        schema_json={},
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    for stage_name in JobStageName:
        db_session.add(
            JobStage(
                job_id=job.id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )
    await db_session.flush()
    return job


def test_stage_for_failed_detail_type_maps_project_submitted_to_intake() -> None:
    assert stage_for_failed_detail_type("eventforge.project.submitted") == JobStageName.INTAKE.value


def test_parse_failed_event_detail_validates_envelope() -> None:
    event = build_project_submitted_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-abc",
        name="Failure parse test",
        schema_json={"type": "object", "properties": {}},
    )
    detail = json.loads(event.model_dump_json())
    parsed = parse_failed_event_detail(detail)
    assert parsed.event_id == event.event_id
    assert parsed.detail_type == "eventforge.project.submitted"


async def test_process_pipeline_failure_marks_job_and_stage_failed(
    db_session: AsyncSession,
) -> None:
    job = await _seed_job_with_stages(db_session)
    failed_event = build_project_submitted_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        name=job.name,
        schema_json={"type": "object", "properties": {}},
    )
    publisher = AsyncMock(spec=EventPublisher)

    result = await process_pipeline_failure(
        db_session,
        publisher,
        failed_event=parse_failed_event_detail(json.loads(failed_event.model_dump_json())),
        error_message="Worker crashed",
        source_queue="eventforge-ingestion",
        receive_count=3,
    )

    assert result is not None
    assert result.detail_type == DETAIL_TYPE_PIPELINE_FAILED
    assert result.payload.stage == JobStageName.INTAKE.value
    assert result.payload.failed_event_id == failed_event.event_id
    assert result.payload.error_message == "Worker crashed"
    assert result.payload.source_queue == "eventforge-ingestion"
    assert result.payload.receive_count == 3
    assert result.event_id == deterministic_pipeline_failed_event_id(job.id, failed_event.event_id)

    await db_session.refresh(job)
    stage_repo = JobStageRepository(db_session)
    intake_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.INTAKE.value)
    assert intake_stage is not None
    assert job.status == JobStatus.FAILED.value
    assert intake_stage.status == StageStatus.FAILED.value
    assert intake_stage.error_detail == "Worker crashed"
    publisher.publish.assert_awaited_once()


async def test_process_pipeline_failure_is_idempotent(db_session: AsyncSession) -> None:
    job = await _seed_job_with_stages(db_session)
    failed_event = parse_failed_event_detail(
        json.loads(
            build_project_submitted_event(
                job_id=job.id,
                correlation_id=job.correlation_id,
                name=job.name,
                schema_json={"type": "object", "properties": {}},
            ).model_dump_json()
        )
    )
    publisher = AsyncMock(spec=EventPublisher)

    first = await process_pipeline_failure(db_session, publisher, failed_event=failed_event)
    second = await process_pipeline_failure(db_session, publisher, failed_event=failed_event)

    assert first is not None
    assert second is None
    assert publisher.publish.await_count == 1


async def test_process_pipeline_failure_still_publishes_when_job_already_failed(
    db_session: AsyncSession,
) -> None:
    """Publish retry after DB commit but before a successful pipeline.failed emit."""
    job = await _seed_job_with_stages(db_session)
    job.status = JobStatus.FAILED.value
    stage_repo = JobStageRepository(db_session)
    intake_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.INTAKE.value)
    assert intake_stage is not None
    await stage_repo.mark_failed(intake_stage, "Prior failure")
    await db_session.flush()

    failed_event = parse_failed_event_detail(
        json.loads(
            build_project_submitted_event(
                job_id=job.id,
                correlation_id=job.correlation_id,
                name=job.name,
                schema_json={"type": "object", "properties": {}},
            ).model_dump_json()
        )
    )
    publisher = AsyncMock(spec=EventPublisher)

    result = await process_pipeline_failure(db_session, publisher, failed_event=failed_event)

    assert result is not None
    publisher.publish.assert_awaited_once()


async def test_process_pipeline_failure_retries_publish_after_release_claim(
    db_session: AsyncSession,
) -> None:
    job = await _seed_job_with_stages(db_session)
    failed_event = parse_failed_event_detail(
        json.loads(
            build_project_submitted_event(
                job_id=job.id,
                correlation_id=job.correlation_id,
                name=job.name,
                schema_json={"type": "object", "properties": {}},
            ).model_dump_json()
        )
    )
    publisher = AsyncMock(spec=EventPublisher)
    publisher.publish.side_effect = [EventPublishError("EventBridge down"), None]

    with pytest.raises(EventPublishError):
        await process_pipeline_failure(db_session, publisher, failed_event=failed_event)

    retry_result = await process_pipeline_failure(db_session, publisher, failed_event=failed_event)

    assert retry_result is not None
    assert publisher.publish.await_count == 2
    await db_session.refresh(job)
    assert job.status == JobStatus.FAILED.value


async def test_dlq_worker_deletes_message_on_success() -> None:
    job_id = UUID("11111111-1111-4111-8111-111111111111")
    event = build_project_submitted_event(
        job_id=job_id,
        correlation_id="corr-dlq",
        name="DLQ worker test",
        schema_json={"type": "object", "properties": {}},
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.project.submitted",
            "source": "eventforge.api",
            "detail": json.loads(event.model_dump_json()),
        }
    )
    message = {
        "Body": body,
        "ReceiptHandle": "receipt-123",
        "MessageId": "msg-123",
        "Attributes": {"ApproximateReceiveCount": "4"},
    }

    worker = DlqWorker()
    worker.handle_message = AsyncMock()
    worker._delete_message = MagicMock()

    with patch.object(worker, "_receive_messages", return_value=([message], False)):
        processed = await worker.poll_once()

    assert processed == 1
    worker.handle_message.assert_awaited_once_with(message)
    worker._delete_message.assert_called_once_with("receipt-123")


def test_parse_eventbridge_sqs_body_works_for_dlq_payload() -> None:
    event = build_project_submitted_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-dlq",
        name="DLQ parse test",
        schema_json={"type": "object", "properties": {}},
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.project.submitted",
            "source": "eventforge.api",
            "detail": json.loads(event.model_dump_json()),
        }
    )
    detail = parse_eventbridge_sqs_body(body)
    parsed = parse_failed_event_detail(detail)
    assert parsed.job_id == event.job_id
    assert parsed.detail_type == "eventforge.project.submitted"
