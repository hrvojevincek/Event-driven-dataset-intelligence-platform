import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.core.config import get_settings
from eventforge.db.models import Job, JobStatus, ProcessedEvent, User
from eventforge.db.repositories import JobRepository, ProcessedEventRepository, UserRepository
from eventforge.db.repositories.user import MOCK_AUTH_SUBJECT_ID
from eventforge.db.session import reset_engine

settings = get_settings()


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


@pytest.mark.asyncio
async def test_user_and_job_repositories(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    job_repo = JobRepository(db_session)

    user = User(email="test@example.com", auth_subject_id="user_test")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id="corr-test-123",
        name="What is event-driven architecture?",
        schema_json="{}",
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    fetched_user = await user_repo.get_by_auth_subject_id("user_test")
    assert fetched_user is not None
    assert fetched_user.id == user.id

    fetched_job = await job_repo.get_by_correlation_id("corr-test-123")
    assert fetched_job is not None
    assert fetched_job.name == job.name
    assert fetched_job.user_id == user.id

    jobs = await job_repo.list_by_user_id(user.id)
    assert len(jobs) == 1
    assert jobs[0].id == job.id


@pytest.mark.asyncio
async def test_processed_event_repository(db_session: AsyncSession) -> None:
    repo = ProcessedEventRepository(db_session)

    assert await repo.exists("evt-001") is False

    db_session.add(ProcessedEvent(event_id="evt-001", worker_name="ingestion"))
    await db_session.flush()

    assert await repo.exists("evt-001") is True
    event = await repo.get_by_event_id("evt-001")
    assert event is not None
    assert event.worker_name == "ingestion"


@pytest.mark.asyncio
async def test_get_or_create_mock_user_is_idempotent(
        db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    first = await repo.get_or_create_mock_user()
    second = await repo.get_or_create_mock_user()

    assert first.id == second.id
    assert first.auth_subject_id == MOCK_AUTH_SUBJECT_ID
    fetched = await repo.get_by_auth_subject_id(MOCK_AUTH_SUBJECT_ID)
    assert fetched is not None
    assert fetched.id == first.id
