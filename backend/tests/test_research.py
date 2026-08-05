import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.agents.research import (
    parse_knowledge_mined_event,
    parse_research_task_dispatched_event,
    process_knowledge_mined,
    process_research_task_dispatched,
)
from eventforge.core.config import get_settings
from eventforge.db.models import (
    DocumentChunk,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    KnowledgeEntity,
    ResearchNote,
    Source,
    StageStatus,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.db.session import reset_engine
from eventforge.events.deterministic import deterministic_research_task_id
from eventforge.events.parser import parse_eventbridge_sqs_body
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    EMBEDDING_DIMENSION,
    WORKER_NAME_RESEARCH,
    WORKER_NAME_RESEARCH_ORCHESTRATOR,
    build_knowledge_mined_event,
    build_research_task_dispatched_event,
)
from eventforge.services.embedding import EmbeddingClient
from eventforge.services.knowledge import expected_research_task_count
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult
from eventforge.services.search.tavily import TavilyClient
from eventforge.workers.research import ResearchWorker

settings = get_settings()

_SUB_QUERIES_JSON = json.dumps(
    ["How does concept alpha relate to parallel research patterns?"]
)
_RESEARCH_NOTE = "## Key findings\n\n- Parallel fan-out improves throughput [RAG-0]."


def _mock_embedding_client() -> EmbeddingClient:
    client = AsyncMock(spec=EmbeddingClient)

    async def _embed(texts: list[str], **kwargs: object) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIMENSION for _ in texts]

    client.embed_texts = AsyncMock(side_effect=_embed)
    return client


def _mock_llm_client() -> LLMClient:
    client = AsyncMock(spec=LLMClient)

    async def _complete(messages: list[object], **kwargs: object) -> LLMCompletionResult:
        system_content = messages[0].content if messages else ""
        if "sub-queries" in system_content:
            content = _SUB_QUERIES_JSON
        else:
            content = _RESEARCH_NOTE
        return LLMCompletionResult(
            content=content,
            model="gpt-4o-mini",
            input_tokens=50,
            output_tokens=120,
            cost_usd=Decimal("0.002"),
        )

    client.complete = AsyncMock(side_effect=_complete)
    return client


def _mock_tavily_client() -> TavilyClient:
    client = AsyncMock(spec=TavilyClient)
    client.search = AsyncMock(return_value=[])
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


async def _seed_job_with_entities(
    db_session: AsyncSession,
    *,
    with_chunks: bool = False,
) -> tuple[Job, JobStage, list[KnowledgeEntity]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"research-{suffix}@example.com", auth_subject_id=f"research-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-research-{suffix}",
        topic="Parallel research patterns",
        depth="standard",
        status=JobStatus.RUNNING.value,
        max_sources=2,
    )
    db_session.add(job)
    await db_session.flush()

    research_stage = JobStage(
        job_id=job.id,
        stage=JobStageName.RESEARCH.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(research_stage)

    entities = [
        KnowledgeEntity(
            job_id=job.id,
            chunk_id=None,
            name=job.topic,
            entity_type="topic",
            task_index=0,
        ),
        KnowledgeEntity(
            job_id=job.id,
            chunk_id=None,
            name="concept alpha",
            entity_type="concept",
            task_index=1,
        ),
    ]
    db_session.add_all(entities)

    if with_chunks:
        source = Source(
            job_id=job.id,
            url="https://example.com/parallel",
            title="Parallel patterns",
            snippet="Fan-out research improves latency.",
        )
        db_session.add(source)
        await db_session.flush()
        chunk = DocumentChunk(
            job_id=job.id,
            source_id=source.id,
            chunk_index=0,
            content="Parallel research agents run focused sub-queries concurrently.",
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )
        db_session.add(chunk)
        entities[1].chunk_id = chunk.id

    await db_session.flush()
    return job, research_stage, entities


def test_parse_knowledge_mined_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_knowledge_mined_event({"detail_type": "eventforge.query.submitted"})


def test_parse_research_task_dispatched_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_research_task_dispatched_event({"detail_type": "eventforge.query.submitted"})


async def test_process_knowledge_mined_dispatches_tasks_and_starts_stage(
    db_session: AsyncSession,
) -> None:
    job, stage, entities = await _seed_job_with_entities(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_knowledge_mined_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        entity_ids=[entity.id for entity in entities],
    )

    result = await process_knowledge_mined(
        db_session,
        mock_publisher,
        inbound,
        llm_client=_mock_llm_client(),
    )

    expected_tasks = expected_research_task_count(entities)
    assert result is not None
    assert len(result) == expected_tasks
    assert mock_publisher.publish.await_count == expected_tasks
    assert result[0].payload.sub_query == json.loads(_SUB_QUERIES_JSON)[0]

    await db_session.refresh(stage)
    assert stage.status == StageStatus.RUNNING.value
    assert stage.started_at is not None

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_RESEARCH_ORCHESTRATOR


async def test_process_knowledge_mined_skips_duplicate_event(db_session: AsyncSession) -> None:
    job, _, entities = await _seed_job_with_entities(db_session)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_knowledge_mined_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        entity_ids=[entity.id for entity in entities],
    )
    llm_client = _mock_llm_client()

    await process_knowledge_mined(db_session, mock_publisher, inbound, llm_client=llm_client)
    mock_publisher.reset_mock()

    duplicate_result = await process_knowledge_mined(
        db_session, mock_publisher, inbound, llm_client=llm_client
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()


async def test_process_research_task_dispatched_writes_note_and_publishes(
    db_session: AsyncSession,
) -> None:
    job, stage, entities = await _seed_job_with_entities(db_session, with_chunks=True)
    mock_publisher = AsyncMock(spec=EventPublisher)

    task_index = 0
    task_id = deterministic_research_task_id(job.id, task_index)
    inbound = build_research_task_dispatched_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=task_id,
        task_index=task_index,
        sub_query="How does concept alpha relate to parallel research?",
        entity_ids=[entity.id for entity in entities],
    )

    result = await process_research_task_dispatched(
        db_session,
        mock_publisher,
        inbound,
        llm_client=_mock_llm_client(),
        embed_client=_mock_embedding_client(),
        search_client=_mock_tavily_client(),
    )

    assert result is not None
    assert result.payload.task_id == task_id
    mock_publisher.publish.assert_awaited_once()

    note = await db_session.scalar(
        select(ResearchNote).where(ResearchNote.job_id == job.id)
    )
    assert note is not None
    assert note.content == _RESEARCH_NOTE
    assert "Mock research" not in note.content

    note_count = await db_session.scalar(
        select(func.count()).select_from(ResearchNote).where(ResearchNote.job_id == job.id)
    )
    assert note_count == 1

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_RESEARCH

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None


async def test_process_research_task_dispatched_completes_stage_when_all_notes_exist(
    db_session: AsyncSession,
) -> None:
    job, stage, entities = await _seed_job_with_entities(db_session, with_chunks=True)
    mock_publisher = AsyncMock(spec=EventPublisher)
    entity_ids = [entity.id for entity in entities]
    expected_tasks = expected_research_task_count(entities)
    llm_client = _mock_llm_client()
    embed_client = _mock_embedding_client()
    search_client = _mock_tavily_client()

    for task_index in range(expected_tasks):
        task_id = deterministic_research_task_id(job.id, task_index)
        inbound = build_research_task_dispatched_event(
            job_id=job.id,
            correlation_id=job.correlation_id,
            task_id=task_id,
            task_index=task_index,
            sub_query=f"Sub-query {task_index}",
            entity_ids=entity_ids,
        )
        await process_research_task_dispatched(
            db_session,
            mock_publisher,
            inbound,
            llm_client=llm_client,
            embed_client=embed_client,
            search_client=search_client,
        )

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None

    note_count = await db_session.scalar(
        select(func.count()).select_from(ResearchNote).where(ResearchNote.job_id == job.id)
    )
    assert note_count == expected_tasks


async def test_process_research_task_dispatched_skips_duplicate_event(
    db_session: AsyncSession,
) -> None:
    job, _, entities = await _seed_job_with_entities(db_session, with_chunks=True)
    mock_publisher = AsyncMock(spec=EventPublisher)
    task_id = deterministic_research_task_id(job.id, 0)
    inbound = build_research_task_dispatched_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_id=task_id,
        task_index=0,
        sub_query="Duplicate task test",
        entity_ids=[entity.id for entity in entities],
    )
    kwargs = {
        "llm_client": _mock_llm_client(),
        "embed_client": _mock_embedding_client(),
        "search_client": _mock_tavily_client(),
    }

    await process_research_task_dispatched(db_session, mock_publisher, inbound, **kwargs)
    mock_publisher.reset_mock()

    duplicate_result = await process_research_task_dispatched(
        db_session, mock_publisher, inbound, **kwargs
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()


async def test_research_worker_deletes_message_on_success() -> None:
    worker = ResearchWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_research_task_dispatched_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        task_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        task_index=0,
        sub_query="Worker routing test",
        entity_ids=[UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")],
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


def test_parse_eventbridge_sqs_body_extracts_research_task_dispatched_detail() -> None:
    event = build_research_task_dispatched_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-abc",
        task_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        task_index=1,
        sub_query="Parsed sub-query",
        entity_ids=[UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")],
    )
    body = json.dumps(
        {
            "version": "0",
            "detail-type": "eventforge.research.task.dispatched",
            "source": "eventforge.workers.research",
            "detail": json.loads(event.model_dump_json()),
        }
    )

    detail = parse_eventbridge_sqs_body(body)
    assert detail["detail_type"] == "eventforge.research.task.dispatched"
    assert detail["payload"]["task_index"] == 1
