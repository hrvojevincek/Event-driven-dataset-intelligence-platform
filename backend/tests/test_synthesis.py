import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.agents.synthesis import (
    _expected_research_task_count,
    parse_research_task_completed_event,
    process_research_task_completed,
)
from eventforge.core.config import get_settings
from eventforge.db.models import (
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    KnowledgeEntity,
    ResearchNote,
    Source,
    StageStatus,
    SynthesisReport,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.db.session import reset_engine
from eventforge.events.deterministic import deterministic_research_task_id
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    WORKER_NAME_SYNTHESIS,
    build_research_task_completed_event,
)
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult
from eventforge.workers.synthesis import SynthesisWorker

settings = get_settings()

_SYNTHESIS_REPORT = (
    "# Executive summary\n\n"
    "Event-driven patterns improve scalability [SRC-0].\n\n"
    "## References\n\n- [SRC-0] Example source"
)


def _mock_llm_client() -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.complete = AsyncMock(
        return_value=LLMCompletionResult(
            content=_SYNTHESIS_REPORT,
            model="gpt-4o-mini",
            input_tokens=200,
            output_tokens=400,
            cost_usd=Decimal("0.004"),
        )
    )
    return client


@pytest.fixture
async def db_session() -> AsyncSession:
    reset_engine()
    engine = create_async_engine(
        settings.async_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
    reset_engine()


async def _seed_job_with_notes(
    db_session: AsyncSession,
    *,
    note_count: int | None = None,
    concept_count: int = 1,
    with_sources: bool = False,
) -> tuple[Job, JobStage, list[ResearchNote]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"synthesis-{suffix}@example.com",
                auth_subject_id=f"synthesis-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-synthesis-{suffix}",
        topic="Synthesis report patterns",
        depth="standard",
        status=JobStatus.RUNNING.value,
        max_sources=2,
    )
    db_session.add(job)
    await db_session.flush()

    synthesis_stage = JobStage(
        job_id=job.id,
        stage=JobStageName.SYNTHESIS.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(synthesis_stage)

    entities = [
        KnowledgeEntity(
            job_id=job.id,
            chunk_id=None,
            name=job.topic,
            entity_type="topic",
            task_index=0,
        ),
    ]
    for index in range(concept_count):
        entities.append(
            KnowledgeEntity(
                job_id=job.id,
                chunk_id=None,
                name=f"concept {index}",
                entity_type="concept",
                task_index=index + 1,
            )
        )
    db_session.add_all(entities)
    await db_session.flush()

    if with_sources:
        db_session.add(
            Source(
                job_id=job.id,
                url="https://example.com/synthesis",
                title="Synthesis patterns guide",
                snippet="Combine parallel research into a cited report.",
            )
        )
        await db_session.flush()

    resolved_note_count = (note_count
                           if note_count is
                           not None else
                           _expected_research_task_count(entities))
    notes = [
        ResearchNote(
            job_id=job.id,
            task_id=deterministic_research_task_id(job.id, index),
            task_index=index,
            sub_query=f"Sub-query {index}",
            content=f"Mock note content {index}",
        )
        for index in range(resolved_note_count)
    ]
    db_session.add_all(notes)
    await db_session.flush()
    return job, synthesis_stage, notes


def test_parse_research_task_completed_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_research_task_completed_event(
            {"detail_type": "eventforge.query.submitted"})


async def test_process_research_task_completed_waits_for_all_notes(
    db_session: AsyncSession,
) -> None:
    job, stage, notes = await _seed_job_with_notes(db_session, note_count=1, concept_count=2)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=notes[0].task_id,
        note_id=notes[0].id,
        task_index=notes[0].task_index,
    )

    result = await process_research_task_completed(
        db_session, mock_publisher, inbound, llm_client=_mock_llm_client()
    )

    assert result is None
    mock_publisher.publish.assert_not_awaited()

    await db_session.refresh(stage)
    assert stage.status == StageStatus.PENDING.value


async def test_process_research_task_completed_writes_report_and_completes_job(
    db_session: AsyncSession,
) -> None:
    job, stage, notes = await _seed_job_with_notes(db_session, with_sources=True)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=notes[-1].task_id,
        note_id=notes[-1].id,
        task_index=notes[-1].task_index,
    )

    result = await process_research_task_completed(
        db_session, mock_publisher, inbound, llm_client=_mock_llm_client()
    )

    assert result is not None
    assert result.payload.note_count == 1
    mock_publisher.publish.assert_awaited_once()

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None

    await db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED.value

    report = await db_session.scalar(
        select(SynthesisReport).where(SynthesisReport.job_id == job.id)
    )
    assert report is not None
    assert report.content == _SYNTHESIS_REPORT
    assert "Mock synthesis" not in report.content

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_SYNTHESIS


async def test_process_research_task_completed_skips_duplicate_trigger(
    db_session: AsyncSession,
) -> None:
    job, _, notes = await _seed_job_with_notes(db_session, concept_count=2)
    mock_publisher = AsyncMock(spec=EventPublisher)

    first = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=notes[0].task_id,
        note_id=notes[0].id,
        task_index=notes[0].task_index,
    )
    second = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=notes[1].task_id,
        note_id=notes[1].id,
        task_index=notes[1].task_index,
    )

    await process_research_task_completed(
        db_session, mock_publisher, first, llm_client=_mock_llm_client()
    )
    mock_publisher.reset_mock()

    duplicate_result = await process_research_task_completed(
        db_session, mock_publisher, second, llm_client=_mock_llm_client()
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()


async def test_process_research_task_completed_is_idempotent_for_same_event(
    db_session: AsyncSession,
) -> None:
    job, _, notes = await _seed_job_with_notes(db_session, concept_count=2)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=notes[-1].task_id,
        note_id=notes[-1].id,
        task_index=notes[-1].task_index,
    )

    llm_client = _mock_llm_client()
    await process_research_task_completed(
        db_session, mock_publisher, inbound, llm_client=llm_client
    )
    mock_publisher.reset_mock()

    duplicate_result = await process_research_task_completed(
        db_session, mock_publisher, inbound, llm_client=llm_client
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()


async def test_synthesis_worker_deletes_message_on_success() -> None:
    worker = SynthesisWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_research_task_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        task_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        note_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        task_index=0,
    )
    body = json.dumps({"detail": json.loads(event.model_dump_json())})
    mock_client.receive_message.return_value = {"Messages": [
        {"ReceiptHandle": "rh-1", "Body": body, "MessageId": "m-1"}]}
    worker._client = mock_client
    worker._queue_url = "http://localstack/000000000000/eventforge-synthesis"

    with patch.object(worker, "handle_message", new=AsyncMock()):
        handled = await worker.poll_once()

    assert handled == 1
    worker._delete_message.assert_called_once_with("rh-1")


def test_parse_eventbridge_sqs_body_extracts_research_task_completed_detail() -> None:
    event = build_research_task_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-abc",
        task_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        note_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        task_index=2,
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.research.task.completed",
            "source": "eventforge.workers.annotation",
            "detail": json.loads(event.model_dump_json()),
        }
    )

    detail = parse_eventbridge_sqs_body(body)
    assert detail["detail_type"] == "eventforge.research.task.completed"
    assert detail["payload"]["task_index"] == 2


def test_build_synthesis_completed_event_sets_payload() -> None:
    from eventforge.events.schemas import build_synthesis_completed_event

    event = build_synthesis_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-out",
        report_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        note_count=3,
    )
    assert event.detail_type == "eventforge.synthesis.completed"
    assert event.payload.note_count == 3
