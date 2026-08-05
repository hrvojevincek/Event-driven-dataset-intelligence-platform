from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_agent
from eventforge.db.models import (
    DocumentChunk,
    Job,
    JobStageName,
    KnowledgeEntity,
)
from eventforge.db.repositories import (
    DocumentChunkRepository,
    JobRepository,
    JobStageRepository,
    KnowledgeEntityRepository,
    ProcessedEventRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import (
    EVENT_SOURCE_KNOWLEDGE,
    EventPublisher,
    EventPublishError,
)
from eventforge.events.schemas import (
    DETAIL_TYPE_KNOWLEDGE_MINED,
    WORKER_NAME_KNOWLEDGE,
    EmbeddingCompletedEvent,
    KnowledgeMinedEvent,
    build_knowledge_mined_event,
)
from eventforge.events.schemas.constants import DETAIL_TYPE_EMBEDDING_COMPLETED
from eventforge.services.embedding import EmbeddingClient, get_embedding_client
from eventforge.services.knowledge import extract_knowledge_entities
from eventforge.services.llm.client import LLMClient, get_llm_client


async def _load_or_create_entities(
    session: AsyncSession,
    job: Job,
    chunks: list[DocumentChunk],
    *,
    embed_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
) -> list[KnowledgeEntity]:
    entity_repo = KnowledgeEntityRepository(session)
    existing = await entity_repo.list_by_job_id(job.id)
    if existing:
        return existing

    settings = get_settings()
    embed_client = embed_client or get_embedding_client(session=session)
    llm_client = llm_client or get_llm_client(session=session)
    chunk_repo = DocumentChunkRepository(session)

    topic_vectors = await embed_client.embed_texts(
        [job.topic],
        job_id=job.id,
        agent_name=WORKER_NAME_KNOWLEDGE,
    )
    retrieved = await chunk_repo.search_similar(
        job.id,
        topic_vectors[0],
        limit=settings.knowledge_rag_top_k,
    )
    if not retrieved:
        retrieved = chunks

    entities = await extract_knowledge_entities(
        llm_client,
        job,
        retrieved,
        max_entities=settings.knowledge_max_entities,
    )
    session.add_all(entities)
    await session.flush()
    return entities


@traced_agent(WORKER_NAME_KNOWLEDGE)
async def process_embedding_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: EmbeddingCompletedEvent,
    *,
    embed_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
) -> KnowledgeMinedEvent | None:
    """Run knowledge mining for one embedding.completed event. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_KNOWLEDGE):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for knowledge mining: {event.job_id}"
        raise ValueError(msg)

    knowledge_stage = await stage_repo.get_by_job_and_stage(
        job.id, JobStageName.KNOWLEDGE_MINING.value
    )
    if knowledge_stage is None:
        msg = f"Knowledge mining stage missing for job: {job.id}"
        raise ValueError(msg)

    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.id.in_(event.payload.chunk_ids))
        .order_by(DocumentChunk.source_id, DocumentChunk.chunk_index)
    )
    chunks = list(result.scalars().all())
    if len(chunks) != len(event.payload.chunk_ids):
        msg = (
            f"Document chunks missing for knowledge mining job: {event.job_id}"
        )
        raise ValueError(msg)

    await stage_repo.mark_running(knowledge_stage)
    entities = await _load_or_create_entities(
        session,
        job,
        chunks,
        embed_client=embed_client,
        llm_client=llm_client,
    )

    completed_event = build_knowledge_mined_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        entity_ids=[entity.id for entity in entities],
        event_id=deterministic_event_id(job.id, DETAIL_TYPE_KNOWLEDGE_MINED),
    )

    await stage_repo.mark_completed(knowledge_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_KNOWLEDGE)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_KNOWLEDGE)
        await session.commit()
        raise

    return completed_event


def parse_embedding_completed_event(detail: dict) -> EmbeddingCompletedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_EMBEDDING_COMPLETED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return EmbeddingCompletedEvent.model_validate(detail)
