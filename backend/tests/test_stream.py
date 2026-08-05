import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.api.deps import get_db, get_publisher
from eventforge.core.config import get_settings as load_settings
from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    StageStatus,
    User,
)
from eventforge.db.repositories import JobStageRepository, UserRepository
from eventforge.db.session import reset_engine
from eventforge.events.publisher import EventPublisher
from eventforge.main import app
from eventforge.services.stage_stream import iter_job_stream_events, parse_stream_event


@pytest.fixture
async def db_session() -> AsyncSession:
    load_settings.cache_clear()
    reset_engine()
    engine = create_async_engine(
        load_settings().async_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
    reset_engine()
    load_settings.cache_clear()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    mock_publisher = AsyncMock(spec=EventPublisher)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_publisher] = lambda: mock_publisher
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _seed_project(db_session: AsyncSession) -> tuple[User, Job]:
    user = await UserRepository(db_session).get_or_create_mock_user()
    job = Job(
        user_id=user.id,
        correlation_id=f"corr-stream-{uuid.uuid4().hex[:8]}",
        name="SSE test project",
        schema_json="{}",
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    for stage_name in PIPELINE_STAGE_NAMES:
        db_session.add(
            JobStage(
                job_id=job.id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )
    await db_session.flush()
    await db_session.commit()
    return user, job


async def test_iter_job_stream_returns_snapshot(
        db_session: AsyncSession) -> None:
    user, job = await _seed_project(db_session)

    events = []
    async for event in iter_job_stream_events(job.id, user.id):
        events.append(event)
        break

    assert len(events) == 1
    snapshot = events[0]
    assert snapshot.event == "snapshot"
    assert snapshot.job_id == job.id
    assert snapshot.job_status == "pending"
    assert snapshot.stages is not None
    assert len(snapshot.stages) == 5
    assert all(stage.status == "pending" for stage in snapshot.stages)


async def test_iter_job_stream_emits_stage_update(
        db_session: AsyncSession) -> None:
    user, job = await _seed_project(db_session)

    stream = iter_job_stream_events(job.id, user.id)
    snapshot = await anext(stream)
    assert snapshot.event == "snapshot"

    intake_stage = await JobStageRepository(db_session).get_by_job_and_stage(
        job.id,
        JobStageName.INTAKE.value,
    )
    assert intake_stage is not None
    await JobStageRepository(db_session).mark_running(intake_stage)
    await db_session.commit()

    update = await anext(stream)
    assert update.event == "stage_update"
    assert update.stage == JobStageName.INTAKE.value
    assert update.status == StageStatus.RUNNING.value


async def test_stream_route_returns_404_for_unknown_job(
        client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/projects/{uuid.uuid4()}/stream")
    assert response.status_code == 404


def test_parse_stream_event_round_trip() -> None:
    raw = (
        '{"event":"stage_update","job_id":"11111111-1111-4111-8111-111111111111",'
        '"correlation_id":"abc","stage":"intake","status":"running",'
        '"timestamp":"2026-06-29T12:00:00+00:00"}')
    parsed = parse_stream_event(raw)
    assert parsed.event == "stage_update"
    assert parsed.stage == "intake"
