import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.api.schemas.queries import (
    JobStageResponse,
    LLMUsageCallResponse,
    LLMUsageSummaryResponse,
    QueryDetailResponse,
    QuerySummaryResponse,
    SourceResponse,
    SynthesisReportResponse,
)
from eventforge.core.otel import agent_span
from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    Job,
    JobStage,
    JobStatus,
    LLMUsage,
    StageStatus,
    User,
)
from eventforge.db.repositories import (
    JobRepository,
    LLMUsageRepository,
    ProcessedEventRepository,
    SourceRepository,
)
from eventforge.events.publisher import PUBLISHER_WORKER_NAME, EventPublisher
from eventforge.events.schemas import QueryDepth, build_query_submitted_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitQueryResult:
    """Identifiers returned after a query is submitted and persisted."""

    job_id: uuid.UUID
    correlation_id: str


async def submit_query(
    session: AsyncSession,
    publisher: EventPublisher,
    user: User,
    *,
    topic: str,
    depth: QueryDepth = QueryDepth.STANDARD,
    max_sources: int | None = None,
) -> SubmitQueryResult:

    job_id = uuid.uuid4()
    correlation_id = uuid.uuid4().hex

    job = Job(
        id=job_id,
        user_id=user.id,
        correlation_id=correlation_id,
        name=topic,
        schema_json="{}",
        status=JobStatus.PENDING.value,
    )
    session.add(job)

    for stage_name in PIPELINE_STAGE_NAMES:
        session.add(
            JobStage(
                job_id=job_id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )

    await session.flush()

    event = build_query_submitted_event(
        job_id=job_id,
        correlation_id=correlation_id,
        topic=topic,
        depth=depth,
        max_sources=max_sources,
    )
    # idempotency
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if await processed_repo.try_claim(event_id, PUBLISHER_WORKER_NAME):
        with agent_span(
            "api",
            "submit_query",
            correlation_id=correlation_id,
            job_id=str(job_id),
            event_id=event_id,
        ):
            await publisher.publish_query_submitted(event)
    else:
        logger.info(
            "Skipped publish; query.submitted already claimed",
            extra={
                "event_id": event_id,
                "job_id": str(job_id),
                "correlation_id": correlation_id,
            },
        )

    await session.commit()

    return SubmitQueryResult(job_id=job_id, correlation_id=correlation_id)


_STAGE_ORDER = {stage.value: index for index, stage in enumerate(PIPELINE_STAGE_NAMES)}


def _job_to_summary_response(job: Job) -> QuerySummaryResponse:
    return QuerySummaryResponse(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.name,
        depth="standard",
        status=job.status,
        max_sources=None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _build_llm_usage_summary(
    records: list[LLMUsage],
    total_cost_usd: Decimal,
) -> LLMUsageSummaryResponse:
    return LLMUsageSummaryResponse(
        total_cost_usd=float(total_cost_usd),
        calls=[
            LLMUsageCallResponse(
                id=record.id,
                agent_name=record.agent_name,
                model=record.model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=float(record.cost_usd),
                created_at=record.created_at,
            )
            for record in records
        ],
    )


def _job_to_detail_response(
    job: Job,
    *,
    sources: list[SourceResponse],
    llm_usage: LLMUsageSummaryResponse,
) -> QueryDetailResponse:
    stages = sorted(
        job.stages,
        key=lambda stage: _STAGE_ORDER.get(stage.stage, len(_STAGE_ORDER)),
    )
    synthesis_report = None
    if job.dataset_export is not None:
        synthesis_report = SynthesisReportResponse(
            id=job.dataset_export.id,
            content=job.dataset_export.export_content,
            created_at=job.dataset_export.created_at,
        )
    return QueryDetailResponse(
        job_id=job.id,
        correlation_id=job.correlation_id,
        topic=job.name,
        depth="standard",
        status=job.status,
        max_sources=None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        stages=[
            JobStageResponse(
                stage=stage.stage,
                status=stage.status,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                duration_ms=stage.duration_ms,
                error_detail=stage.error_detail,
            )
            for stage in stages
        ],
        sources=sources,
        synthesis_report=synthesis_report,
        llm_usage=llm_usage,
    )


async def list_queries(
    session: AsyncSession, user: User
) -> list[QuerySummaryResponse]:
    jobs = await JobRepository(session).list_by_user_id(user.id)
    return [_job_to_summary_response(job) for job in jobs]


async def delete_query(
    session: AsyncSession,
    job_id: uuid.UUID,
    user: User,
) -> bool:
    """Delete a job and its related records for the current user."""
    deleted = await JobRepository(session).delete_for_user(job_id, user.id)
    if not deleted:
        return False
    await session.commit()
    return True


async def get_query_detail(
    session: AsyncSession,
    job_id: uuid.UUID,
    user: User,
) -> QueryDetailResponse | None:
    job = await JobRepository(session).get_by_id(job_id)
    if job is None or job.user_id != user.id:
        return None

    usage_repo = LLMUsageRepository(session)
    records = await usage_repo.list_by_job_id(job_id)
    total_cost = await usage_repo.total_cost_by_job_id(job_id)
    llm_usage = _build_llm_usage_summary(records, total_cost)

    source_records = await SourceRepository(session).list_by_job_id(job_id)
    sources = [
        SourceResponse(
            id=source.id,
            url=source.storage_uri,
            title=source.filename,
            snippet=source.provenance or "",
            created_at=source.created_at,
        )
        for source in source_records
    ]

    return _job_to_detail_response(job, sources=sources, llm_usage=llm_usage)
