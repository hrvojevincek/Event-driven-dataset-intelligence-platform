from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.otel import traced_agent
from eventforge.db.models import (
    Job,
    JobStageName,
    JobStatus,
    Source,
    StageStatus,
)
from eventforge.db.repositories import (
    JobRepository,
    JobStageRepository,
    ProcessedEventRepository,
    SourceRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import (
    EVENT_SOURCE_INGESTION,
    EventPublisher,
    EventPublishError,
)
from eventforge.events.schemas import (
    DETAIL_TYPE_INGESTION_COMPLETED,
    WORKER_NAME_INGESTION,
    IngestionCompletedEvent,
    QuerySubmittedEvent,
    build_ingestion_completed_event,
)
from eventforge.events.schemas.constants import DETAIL_TYPE_QUERY_SUBMITTED
from eventforge.services.search import (
    TavilyClient,
    get_tavily_client,
    resolve_source_count,
    resolve_tavily_search_depth,
)


async def _load_or_create_sources(
    session: AsyncSession,
    job: Job,
    search_client: TavilyClient | None = None,
) -> list[Source]:
    source_repo = SourceRepository(session)
    existing = await source_repo.list_by_job_id(job.id)
    if existing:
        return existing

    client = search_client or get_tavily_client()
    max_results = resolve_source_count(
        depth=job.depth, max_sources=job.max_sources
    )
    search_depth = resolve_tavily_search_depth(job.depth)
    results = await client.search(
        job.topic,
        max_results=max_results,
        search_depth=search_depth,
    )
    if not results:
        msg = f"Tavily returned no results for job {job.id}"
        raise ValueError(msg)

    sources = [
        Source(
            job_id=job.id,
            url=result.url,
            title=result.title,
            snippet=result.snippet,
        )
        for result in results[:max_results]
    ]
    session.add_all(sources)
    await session.flush()
    return sources


@traced_agent(WORKER_NAME_INGESTION)
async def process_query_submitted(
    session: AsyncSession,
    publisher: EventPublisher,
    event: QuerySubmittedEvent,
    *,
    search_client: TavilyClient | None = None,
) -> IngestionCompletedEvent | None:
    """Run ingestion for one query.submitted event. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_INGESTION):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for ingestion: {event.job_id}"
        raise ValueError(msg)

    ingestion_stage = await stage_repo.get_by_job_and_stage(
        job.id, JobStageName.INGESTION.value
    )
    if ingestion_stage is None:
        msg = f"Ingestion stage missing for job: {job.id}"
        raise ValueError(msg)

    job.status = JobStatus.RUNNING.value
    if ingestion_stage.status != StageStatus.COMPLETED.value:
        await stage_repo.mark_running(ingestion_stage)

    sources = await _load_or_create_sources(session, job, search_client)

    completed_event = build_ingestion_completed_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        source_ids=[source.id for source in sources],
        event_id=deterministic_event_id(
            job.id, DETAIL_TYPE_INGESTION_COMPLETED
        ),
    )

    await stage_repo.mark_completed(ingestion_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_INGESTION)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_INGESTION)
        await session.commit()
        raise

    return completed_event


def parse_query_submitted_event(detail: dict) -> QuerySubmittedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_QUERY_SUBMITTED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return QuerySubmittedEvent.model_validate(detail)
