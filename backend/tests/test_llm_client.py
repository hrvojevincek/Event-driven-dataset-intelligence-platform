import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.core.config import Settings, get_settings
from eventforge.db.models import Job, JobStatus, User
from eventforge.db.repositories import LLMUsageRepository
from eventforge.db.session import reset_engine
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult, LLMMessage

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


@pytest.fixture
def llm_settings() -> Settings:
    return Settings(
        openai_api_key="test-openai",
        anthropic_api_key="test-anthropic",
        llm_default_model="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_llm_usage_repository_log_and_total(db_session: AsyncSession) -> None:
    user = User(email="llm-cost@example.com", auth_subject_id="llm-cost-user")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id="corr-llm-cost",
        name="LLM cost tracking",
        schema_json={},
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    repo = LLMUsageRepository(db_session)
    await repo.log(
        job_id=job.id,
        agent_name="intake",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal("0.000045"),
    )
    await repo.log(
        job_id=job.id,
        agent_name="export",
        model="gpt-4o-mini",
        input_tokens=200,
        output_tokens=100,
        cost_usd=Decimal("0.000090"),
    )
    await db_session.flush()

    records = await repo.list_by_job_id(job.id)
    assert len(records) == 2
    assert records[0].agent_name == "intake"
    assert await repo.total_cost_by_job_id(job.id) == Decimal("0.000135")


async def _await_operation(_key: str, operation, **_kwargs):
    return await operation()


@pytest.mark.asyncio
async def test_llm_client_logs_usage_when_session_bound(
    db_session: AsyncSession,
    llm_settings: Settings,
) -> None:
    user = User(email="llm-client@example.com", auth_subject_id="llm-client-user")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id="corr-llm-client",
        name="LLM client test",
        schema_json={},
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    mock_result = LLMCompletionResult(
        content="Hello",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        cost_usd=Decimal("0.0000045"),
    )

    client = LLMClient(settings=llm_settings, session=db_session)
    with patch.object(
        client,
        "_get_provider",
        return_value=AsyncMock(complete=AsyncMock(return_value=mock_result)),
    ), patch(
        "eventforge.services.llm.client.call_with_resilience",
        side_effect=_await_operation,
    ):
        result = await client.complete(
            [LLMMessage(role="user", content="Hi")],
            job_id=job.id,
            agent_name="research",
        )

    assert result.content == "Hello"
    records = await LLMUsageRepository(db_session).list_by_job_id(job.id)
    assert len(records) == 1
    assert records[0].agent_name == "research"
    assert records[0].input_tokens == 10


@pytest.mark.asyncio
async def test_llm_client_returns_result_when_logging_fails(
    db_session: AsyncSession,
    llm_settings: Settings,
) -> None:
    mock_result = LLMCompletionResult(
        content="Hello",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        cost_usd=Decimal("0.0000045"),
    )

    client = LLMClient(settings=llm_settings, session=db_session)
    with patch.object(
        client,
        "_get_provider",
        return_value=AsyncMock(complete=AsyncMock(return_value=mock_result)),
    ), patch.object(
        LLMUsageRepository,
        "log",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ), patch(
        "eventforge.services.llm.client.call_with_resilience",
        side_effect=_await_operation,
    ):
        result = await client.complete(
            [LLMMessage(role="user", content="Hi")],
            job_id=uuid.uuid4(),
            agent_name="research",
        )

    assert result.content == "Hello"


@pytest.mark.asyncio
async def test_llm_client_routes_to_anthropic_model(llm_settings: Settings) -> None:
    mock_result = LLMCompletionResult(
        content="Claude says hi",
        model="claude-3-5-haiku-20241022",
        input_tokens=12,
        output_tokens=6,
        cost_usd=Decimal("0.0000336"),
    )
    provider = AsyncMock(complete=AsyncMock(return_value=mock_result))

    client = LLMClient(settings=llm_settings)
    with patch.object(client, "_get_provider", return_value=provider) as get_provider, patch(
        "eventforge.services.llm.client.call_with_resilience",
        side_effect=_await_operation,
    ):
        result = await client.complete(
            [LLMMessage(role="user", content="Hi")],
            job_id=uuid.uuid4(),
            agent_name="knowledge",
            model="claude-3-5-haiku-20241022",
        )

    get_provider.assert_called_once_with("anthropic")
    provider.complete.assert_awaited_once()
    assert result.model.startswith("claude")
