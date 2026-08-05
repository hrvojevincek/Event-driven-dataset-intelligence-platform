from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.otel import traced_agent
from eventforge.db.models import (
    Job,
    JobStageName,
    KnowledgeEntity,
    ResearchNote,
)
from eventforge.db.repositories import (
    JobRepository,
    JobStageRepository,
    KnowledgeEntityRepository,
    ProcessedEventRepository,
    ResearchNoteRepository,
)
from eventforge.events.deterministic import (
    deterministic_event_id,
    deterministic_research_task_id,
)
from eventforge.events.publisher import (
    EVENT_SOURCE_RESEARCH,
    EventPublisher,
    EventPublishError,
)
from eventforge.events.schemas import (
    DETAIL_TYPE_RESEARCH_TASK_COMPLETED,
    DETAIL_TYPE_RESEARCH_TASK_DISPATCHED,
    WORKER_NAME_RESEARCH,
    WORKER_NAME_RESEARCH_ORCHESTRATOR,
    KnowledgeMinedEvent,
    ResearchTaskCompletedEvent,
    ResearchTaskDispatchedEvent,
    build_research_task_completed_event,
    build_research_task_dispatched_event,
)
from eventforge.events.schemas.constants import DETAIL_TYPE_KNOWLEDGE_MINED
from eventforge.services.knowledge import (
    expected_research_task_count,
    research_entities_for_fanout,
)
from eventforge.services.legacy.embedding import EmbeddingClient, get_embedding_client
from eventforge.services.llm.client import LLMClient, get_llm_client
from eventforge.services.research import (
    generate_research_note,
    generate_sub_queries,
)
from eventforge.services.search.tavily import TavilyClient, get_tavily_client


async def _build_dispatched_events(
    event: KnowledgeMinedEvent,
    job: Job,
    entities: list[KnowledgeEntity],
    *,
    llm_client: LLMClient,
) -> list[ResearchTaskDispatchedEvent]:
    research_targets = research_entities_for_fanout(entities)
    sub_queries = await generate_sub_queries(llm_client, job, research_targets)
    all_entity_ids = [entity.id for entity in entities]
    dispatched: list[ResearchTaskDispatchedEvent] = []
    for task_index, (_, sub_query) in enumerate(zip(research_targets, sub_queries, strict=True)):
        task_id = deterministic_research_task_id(job.id, task_index)
        dispatched.append(
            build_research_task_dispatched_event(
                job_id=job.id,
                correlation_id=event.correlation_id,
                task_id=task_id,
                task_index=task_index,
                sub_query=sub_query,
                entity_ids=all_entity_ids,
                event_id=deterministic_event_id(
                    job.id,
                    f"{DETAIL_TYPE_RESEARCH_TASK_DISPATCHED}:{task_index}",
                ),
            )
        )
    return dispatched


async def _load_or_create_note(
    session: AsyncSession,
    job: Job,
    task: ResearchTaskDispatchedEvent,
    entities: list[KnowledgeEntity],
    *,
    llm_client: LLMClient,
    embed_client: EmbeddingClient,
    search_client: TavilyClient | None = None,
) -> ResearchNote:
    note_repo = ResearchNoteRepository(session)
    existing = await note_repo.get_by_task_id(task.payload.task_id)
    if existing is not None:
        return existing

    research_targets = research_entities_for_fanout(entities)
    focus_entity = (
        research_targets[task.payload.task_index]
        if task.payload.task_index < len(research_targets)
        else None
    )

    content = await generate_research_note(
        session,
        llm_client,
        embed_client,
        job,
        task.payload.sub_query,
        focus_entity,
        search_client=search_client,
    )

    note = ResearchNote(
        job_id=job.id,
        task_id=task.payload.task_id,
        task_index=task.payload.task_index,
        sub_query=task.payload.sub_query,
        content=content,
    )
    session.add(note)
    await session.flush()
    return note


@traced_agent(WORKER_NAME_RESEARCH_ORCHESTRATOR)
async def prepare_research_fanout(
    session: AsyncSession,
    event: KnowledgeMinedEvent,
    *,
    llm_client: LLMClient | None = None,
) -> list[ResearchTaskDispatchedEvent] | None:
    """Build research sub-tasks from knowledge.mined without publishing events."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_RESEARCH_ORCHESTRATOR):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)
    entity_repo = KnowledgeEntityRepository(session)
    llm_client = llm_client or get_llm_client(session=session)

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for research fan-out: {event.job_id}"
        raise ValueError(msg)

    research_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.RESEARCH.value)
    if research_stage is None:
        msg = f"Research stage missing for job: {job.id}"
        raise ValueError(msg)

    entities = await entity_repo.list_by_ids(event.payload.entity_ids)
    if len(entities) != len(event.payload.entity_ids):
        msg = f"Knowledge entities missing for research job: {event.job_id}"
        raise ValueError(msg)

    await stage_repo.mark_running(research_stage)
    dispatched_events = await _build_dispatched_events(event, job, entities, llm_client=llm_client)
    await session.commit()
    return dispatched_events


@traced_agent(WORKER_NAME_RESEARCH_ORCHESTRATOR)
async def process_knowledge_mined(
    session: AsyncSession,
    publisher: EventPublisher,
    event: KnowledgeMinedEvent,
    *,
    llm_client: LLMClient | None = None,
) -> list[ResearchTaskDispatchedEvent] | None:
    """Fan out research sub-tasks from knowledge.mined. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    dispatched_events = await prepare_research_fanout(session, event, llm_client=llm_client)
    if dispatched_events is None:
        return None

    try:
        for dispatched in dispatched_events:
            await publisher.publish(dispatched, source=EVENT_SOURCE_RESEARCH)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_RESEARCH_ORCHESTRATOR)
        await session.commit()
        raise

    return dispatched_events


@traced_agent(WORKER_NAME_RESEARCH)
async def process_research_task_dispatched(
    session: AsyncSession,
    publisher: EventPublisher,
    event: ResearchTaskDispatchedEvent,
    *,
    llm_client: LLMClient | None = None,
    embed_client: EmbeddingClient | None = None,
    search_client: TavilyClient | None = None,
    step_functions_task_token: str | None = None,
) -> ResearchTaskCompletedEvent | None:
    """Run one research sub-task. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_RESEARCH):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)
    note_repo = ResearchNoteRepository(session)
    entity_repo = KnowledgeEntityRepository(session)
    llm_client = llm_client or get_llm_client(session=session)
    embed_client = embed_client or get_embedding_client(session=session)
    search_client = search_client or get_tavily_client()

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for research task: {event.job_id}"
        raise ValueError(msg)

    research_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.RESEARCH.value)
    if research_stage is None:
        msg = f"Research stage missing for job: {job.id}"
        raise ValueError(msg)

    entities = await entity_repo.list_by_ids(event.payload.entity_ids)
    note = await _load_or_create_note(
        session,
        job,
        event,
        entities,
        llm_client=llm_client,
        embed_client=embed_client,
        search_client=search_client,
    )

    completed_event = build_research_task_completed_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        task_id=event.payload.task_id,
        note_id=note.id,
        task_index=event.payload.task_index,
        event_id=deterministic_event_id(
            job.id,
            f"{DETAIL_TYPE_RESEARCH_TASK_COMPLETED}:{event.payload.task_index}",
        ),
    )

    expected_tasks = expected_research_task_count(entities)
    note_count = await note_repo.count_by_job_id(job.id)
    if note_count >= expected_tasks:
        await stage_repo.mark_completed(research_stage)

    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_RESEARCH)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_RESEARCH)
        await session.commit()
        raise

    if step_functions_task_token:
        from eventforge.services.step_functions import send_task_success

        send_task_success(
            step_functions_task_token,
            completed_event.model_dump(mode="json"),
        )

    return completed_event


def parse_knowledge_mined_event(detail: dict) -> KnowledgeMinedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_KNOWLEDGE_MINED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return KnowledgeMinedEvent.model_validate(detail)


def parse_research_task_dispatched_event(
    detail: dict,
) -> ResearchTaskDispatchedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_RESEARCH_TASK_DISPATCHED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return ResearchTaskDispatchedEvent.model_validate(detail)
