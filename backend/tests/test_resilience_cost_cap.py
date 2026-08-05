import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.core.config import Settings, get_settings
from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    StageStatus,
    User,
)
from eventforge.db.repositories import LLMUsageRepository
from eventforge.db.session import reset_engine
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import build_embedding_completed_event
from eventforge.services.resilience import (
    JobCostCapExceededError,
    assert_job_under_cost_cap,
    emit_cost_cap_pipeline_failure,
)

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


async def _seed_job(db_session: AsyncSession) -> Job:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"cost-cap-{suffix}@example.com",
        auth_subject_id=f"cost-cap-user-{suffix}",
    )
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-cost-cap-{suffix}",
        topic="Cost cap enforcement",
        depth="standard",
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest.mark.asyncio
async def test_assert_job_under_cost_cap_raises_when_at_limit(db_session: AsyncSession) -> None:
    job = await _seed_job(db_session)
    capped_settings = Settings(job_max_cost_usd=Decimal("0.000100"))

    await LLMUsageRepository(db_session).log(
        job_id=job.id,
        agent_name="research",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal("0.000100"),
    )
    await db_session.flush()

    with pytest.raises(JobCostCapExceededError) as exc_info:
        await assert_job_under_cost_cap(db_session, job.id, capped_settings)

    assert exc_info.value.job_id == job.id
    assert exc_info.value.cap_usd == Decimal("0.000100")


@pytest.mark.asyncio
async def test_assert_job_under_cost_cap_skipped_when_unconfigured(
    db_session: AsyncSession,
) -> None:
    job = await _seed_job(db_session)
    await assert_job_under_cost_cap(db_session, job.id, Settings(job_max_cost_usd=None))


@pytest.mark.asyncio
async def test_emit_cost_cap_pipeline_failure_marks_job_failed(db_session: AsyncSession) -> None:
    from eventforge.db.repositories import JobRepository, JobStageRepository

    job = await _seed_job(db_session)
    for stage_name in PIPELINE_STAGE_NAMES:
        db_session.add(
            JobStage(
                job_id=job.id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )
    await db_session.flush()

    # Knowledge worker consumes embedding.completed; stage_mapping marks KNOWLEDGE_MINING failed.
    event = build_embedding_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        chunk_ids=[uuid.uuid4()],
    )
    detail = event.model_dump(mode="json")
    exc = JobCostCapExceededError(
        job.id,
        total_cost_usd=Decimal("0.50"),
        cap_usd=Decimal("0.25"),
    )
    publisher = AsyncMock(spec=EventPublisher)

    await emit_cost_cap_pipeline_failure(db_session, publisher, detail, exc)

    publisher.publish.assert_awaited_once()
    refreshed = await JobRepository(db_session).get_by_id(job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.FAILED.value

    knowledge_stage = await JobStageRepository(db_session).get_by_job_and_stage(
        job.id,
        JobStageName.KNOWLEDGE_MINING.value,
    )
    assert knowledge_stage is not None
    assert knowledge_stage.status == StageStatus.FAILED.value
