import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.agents.ingestion import (
    parse_query_submitted_event,
    process_query_submitted,
)
from eventforge.core.config import get_settings
from eventforge.db.models import Job, JobStage, JobStageName, JobStatus, Source, StageStatus, User
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.db.session import reset_engine
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    WORKER_NAME_INGESTION,
    QueryDepth,
    build_ingestion_completed_event,
    build_query_submitted_event,
)
from eventforge.services.search import DEFAULT_SOURCE_COUNT_BY_DEPTH, TavilyClient
from eventforge.services.search.types import WebSearchResult
from eventforge.workers.intake import IntakeWorker

settings = get_settings()


def _mock_search_results(count: int) -> list[WebSearchResult]:
    return [
        WebSearchResult(
            url=f"https://example.org/source/{index}",
            title=f"Source {index}",
            snippet=f"Content about the topic (source {index}).",
        )
        for index in range(1, count + 1)
    ]


def _mock_tavily_client(max_results: int) -> TavilyClient:
    client = AsyncMock(spec=TavilyClient)
    client.search = AsyncMock(return_value=_mock_search_results(max_results))
    return client


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


async def _seed_job(db_session: AsyncSession) -> tuple[Job, JobStage]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"ingest-{suffix}@example.com", auth_subject_id=f"ingest-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-ingest-{suffix}",
        topic="Event-driven systems",
        depth="standard",
        status=JobStatus.PENDING.value,
        max_sources=2,
    )
    db_session.add(job)
    await db_session.flush()

    stage = JobStage(
        job_id=job.id,
        stage=JobStageName.INGESTION.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(stage)
    await db_session.flush()
    return job, stage


def test_parse_eventbridge_sqs_body_extracts_detail() -> None:
    event = build_query_submitted_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-abc",
        topic="Parse test",
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.query.submitted",
            "source": "eventforge.api",
            "detail": json.loads(event.model_dump_json()),
        }
    )

    detail = parse_eventbridge_sqs_body(body)
    assert detail["detail_type"] == "eventforge.query.submitted"
    assert detail["payload"]["topic"] == "Parse test"


def test_parse_query_submitted_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_query_submitted_event({"detail_type": "eventforge.ingestion.completed"})


async def test_process_query_submitted_writes_sources_and_updates_stage(
    db_session: AsyncSession,
) -> None:
    job, stage = await _seed_job(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_query_submitted_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.topic,
    )

    result = await process_query_submitted(
        db_session,
        mock_publisher,
        inbound,
        search_client=_mock_tavily_client(2),
    )

    assert result is not None
    assert result.payload.source_count == 2
    mock_publisher.publish.assert_awaited_once()

    await db_session.refresh(job)
    await db_session.refresh(stage)
    assert job.status == JobStatus.RUNNING.value
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None

    source_count = await db_session.scalar(
        select(func.count()).select_from(Source).where(Source.job_id == job.id)
    )
    assert source_count == 2

    processed = ProcessedEventRepository(db_session)
    assert await processed.exists(str(inbound.event_id)) is True
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_INGESTION


async def test_process_query_submitted_skips_duplicate_event(db_session: AsyncSession) -> None:
    job, _ = await _seed_job(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_query_submitted_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.topic,
    )

    await process_query_submitted(
        db_session,
        mock_publisher,
        inbound,
        search_client=_mock_tavily_client(2),
    )
    mock_publisher.reset_mock()

    duplicate_result = await process_query_submitted(
        db_session,
        mock_publisher,
        inbound,
        search_client=_mock_tavily_client(2),
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()

    # Duplicate SQS delivery must not create a second batch of sources.
    source_count = await db_session.scalar(
        select(func.count()).select_from(Source).where(Source.job_id == job.id)
    )
    assert source_count == 2


async def test_try_claim_is_atomic_for_repeated_attempts(db_session: AsyncSession) -> None:
    repo = ProcessedEventRepository(db_session)
    event_id = str(uuid.uuid4())

    assert await repo.try_claim(event_id, WORKER_NAME_INGESTION) is True
    # Second claim for the same (event_id, worker) loses.
    assert await repo.try_claim(event_id, WORKER_NAME_INGESTION) is False


async def test_try_claim_scopes_by_worker_name(db_session: AsyncSession) -> None:
    """The API publisher and ingestion worker must claim the same event_id."""
    repo = ProcessedEventRepository(db_session)
    event_id = str(uuid.uuid4())

    assert await repo.try_claim(event_id, "api") is True
    assert await repo.try_claim(event_id, WORKER_NAME_INGESTION) is True


async def test_process_succeeds_when_api_already_claimed_event(db_session: AsyncSession) -> None:
    """Regression: API claiming the event must not block the ingestion worker."""
    job, stage = await _seed_job(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_query_submitted_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.topic,
    )

    # Simulate the API publisher having claimed this event_id.
    repo = ProcessedEventRepository(db_session)
    assert await repo.try_claim(str(inbound.event_id), "api") is True

    result = await process_query_submitted(
        db_session,
        mock_publisher,
        inbound,
        search_client=_mock_tavily_client(2),
    )

    assert result is not None
    mock_publisher.publish.assert_awaited_once()
    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value


async def test_process_query_submitted_uses_default_source_count(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"default-{suffix}@example.com", auth_subject_id=f"default-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-default-{suffix}",
        topic="Defaults",
        depth="standard",
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(
        JobStage(
            job_id=job.id,
            stage=JobStageName.INGESTION.value,
            status=StageStatus.PENDING.value,
        )
    )
    await db_session.flush()

    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_query_submitted_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.topic,
    )

    default_count = DEFAULT_SOURCE_COUNT_BY_DEPTH[QueryDepth.STANDARD]
    result = await process_query_submitted(
        db_session,
        mock_publisher,
        inbound,
        search_client=_mock_tavily_client(default_count),
    )
    assert result is not None
    assert result.payload.source_count == default_count


async def test_ingestion_worker_deletes_message_on_success() -> None:
    worker = IntakeWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_query_submitted_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        topic="Worker test",
    )
    body = json.dumps({"detail": json.loads(event.model_dump_json())})
    mock_client.receive_message.return_value = {
        "Messages": [{"ReceiptHandle": "rh-1", "Body": body, "MessageId": "m-1"}]
    }
    worker._client = mock_client
    worker._queue_url = "http://localstack/000000000000/eventforge-ingestion"

    with patch.object(worker, "handle_message", new=AsyncMock()):
        handled = await worker.poll_once()

    assert handled == 1
    worker._delete_message.assert_called_once_with("rh-1")


def test_build_ingestion_completed_event_sets_payload() -> None:
    source_ids = [
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    event = build_ingestion_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-out",
        source_ids=source_ids,
    )
    assert event.detail_type == "eventforge.ingestion.completed"
    assert event.payload.source_count == 2
    assert event.payload.source_ids == source_ids
