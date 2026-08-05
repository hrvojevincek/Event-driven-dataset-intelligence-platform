import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.agents.knowledge import (
    parse_embedding_completed_event,
    process_embedding_completed,
)
from eventforge.core.config import get_settings
from eventforge.db.models import (
    DocumentChunk,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    KnowledgeEntity,
    Source,
    StageStatus,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.db.session import reset_engine
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    EMBEDDING_DIMENSION,
    WORKER_NAME_KNOWLEDGE,
    build_embedding_completed_event,
)
from eventforge.services.legacy.embedding import EmbeddingClient
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult
from eventforge.workers.knowledge import KnowledgeWorker

settings = get_settings()

_EXTRACTION_JSON = json.dumps(
    [
        {"name": "knowledge graphs", "entity_type": "concept", "source_chunk_index": 0},
        {"name": "entity extraction", "entity_type": "concept", "source_chunk_index": 1},
    ]
)


def _mock_embedding_client() -> EmbeddingClient:
    client = AsyncMock(spec=EmbeddingClient)

    async def _embed(texts: list[str], **kwargs: object) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIMENSION for _ in texts]

    client.embed_texts = AsyncMock(side_effect=_embed)
    return client


def _mock_llm_client() -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.complete = AsyncMock(
        return_value=LLMCompletionResult(
            content=_EXTRACTION_JSON,
            model="gpt-4o-mini",
            input_tokens=50,
            output_tokens=80,
            cost_usd=Decimal("0.001"),
        )
    )
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


async def _seed_job_with_chunks(
    db_session: AsyncSession,
) -> tuple[Job, JobStage, list[DocumentChunk]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"knowledge-{suffix}@example.com", auth_subject_id=f"knowledge-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-knowledge-{suffix}",
        topic="Knowledge mining patterns",
        depth="standard",
        status=JobStatus.RUNNING.value,
        max_sources=2,
    )
    db_session.add(job)
    await db_session.flush()

    knowledge_stage = JobStage(
        job_id=job.id,
        stage=JobStageName.KNOWLEDGE_MINING.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(knowledge_stage)

    source = Source(
        job_id=job.id,
        url=f"https://example.com/{job.id}/1",
        title="Source 1",
        snippet="First snippet about knowledge graphs.",
    )
    db_session.add(source)
    await db_session.flush()

    chunks = [
        DocumentChunk(
            job_id=job.id,
            source_id=source.id,
            chunk_index=index,
            content=f"Entity-rich content chunk {index + 1} about graphs.",
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )
        for index in range(2)
    ]
    db_session.add_all(chunks)
    await db_session.flush()
    return job, knowledge_stage, chunks


def test_parse_embedding_completed_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_embedding_completed_event({"detail_type": "eventforge.query.submitted"})


async def test_process_embedding_completed_writes_entities_and_updates_stage(
    db_session: AsyncSession,
) -> None:
    job, stage, chunks = await _seed_job_with_chunks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    embed_client = _mock_embedding_client()
    llm_client = _mock_llm_client()

    inbound = build_embedding_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        chunk_ids=[chunk.id for chunk in chunks],
    )

    result = await process_embedding_completed(
        db_session,
        mock_publisher,
        inbound,
        embed_client=embed_client,
        llm_client=llm_client,
    )

    assert result is not None
    assert result.payload.entity_count == 3
    mock_publisher.publish.assert_awaited_once()
    embed_client.embed_texts.assert_awaited_once()
    llm_client.complete.assert_awaited_once()

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None

    entity_count = await db_session.scalar(
        select(func.count()).select_from(KnowledgeEntity).where(KnowledgeEntity.job_id == job.id)
    )
    assert entity_count == 3

    from eventforge.db.repositories import KnowledgeEntityRepository

    entities = await KnowledgeEntityRepository(db_session).list_by_job_id(job.id)
    topic_entity = next(entity for entity in entities if entity.entity_type == "topic")
    assert topic_entity.name == job.topic
    assert topic_entity.chunk_id is None

    concept_names = {entity.name for entity in entities if entity.entity_type == "concept"}
    assert concept_names == {"knowledge graphs", "entity extraction"}

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_KNOWLEDGE


async def test_process_embedding_completed_skips_duplicate_event(db_session: AsyncSession) -> None:
    job, _, chunks = await _seed_job_with_chunks(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    embed_client = _mock_embedding_client()
    llm_client = _mock_llm_client()
    inbound = build_embedding_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        chunk_ids=[chunk.id for chunk in chunks],
    )

    await process_embedding_completed(
        db_session,
        mock_publisher,
        inbound,
        embed_client=embed_client,
        llm_client=llm_client,
    )
    mock_publisher.reset_mock()

    duplicate_result = await process_embedding_completed(
        db_session,
        mock_publisher,
        inbound,
        embed_client=embed_client,
        llm_client=llm_client,
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()

    entity_count = await db_session.scalar(
        select(func.count()).select_from(KnowledgeEntity).where(KnowledgeEntity.job_id == job.id)
    )
    assert entity_count == 3


async def test_knowledge_worker_deletes_message_on_success() -> None:
    worker = KnowledgeWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_embedding_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        chunk_ids=[UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")],
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


def test_parse_eventbridge_sqs_body_extracts_embedding_completed_detail() -> None:
    event = build_embedding_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-abc",
        chunk_ids=[UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")],
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.embedding.completed",
            "source": "eventforge.workers.embedding",
            "detail": json.loads(event.model_dump_json()),
        }
    )

    detail = parse_eventbridge_sqs_body(body)
    assert detail["detail_type"] == "eventforge.embedding.completed"
    assert detail["payload"]["chunk_count"] == 1


def test_build_knowledge_mined_event_sets_payload() -> None:
    from eventforge.events.schemas import build_knowledge_mined_event

    entity_ids = [
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    event = build_knowledge_mined_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-out",
        entity_ids=entity_ids,
    )
    assert event.detail_type == "eventforge.knowledge.mined"
    assert event.payload.entity_count == 2
    assert event.payload.entity_ids == entity_ids
