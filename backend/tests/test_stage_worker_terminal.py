"""StageWorker records terminal ValueError/RuntimeError for the UI."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eventforge.core.config import get_settings
from eventforge.db.models import Job, JobStage, JobStageName, JobStatus, StageStatus, User
from eventforge.db.session import reset_engine
from eventforge.events.schemas import build_intake_completed_event
from eventforge.workers.preprocessing import PreprocessingWorker

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


async def test_stage_worker_records_terminal_value_error(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"term-{suffix}@example.com", auth_subject_id=f"term-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-term-{suffix}",
        name="Terminal failure",
        schema_json={},
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()
    for stage_name in JobStageName:
        db_session.add(
            JobStage(
                job_id=job.id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )
    await db_session.commit()

    inbound = build_intake_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        asset_ids=[uuid.uuid4()],
    )
    message = {
        "MessageId": "msg-terminal",
        "Body": json.dumps({"detail": json.loads(inbound.model_dump_json())}),
        "Attributes": {"ApproximateReceiveCount": "1"},
    }

    worker = PreprocessingWorker()
    worker._publisher = AsyncMock()
    worker._session_factory = async_sessionmaker(
        db_session.bind, expire_on_commit=False
    )

    with patch.object(
        worker,
        "process_message",
        new=AsyncMock(side_effect=ValueError("ASR produced no segments for call_001.wav")),
    ):
        await worker.handle_message(message)

    await db_session.refresh(job)
    assert job.status == JobStatus.FAILED.value

    stage = (
        await db_session.execute(
            select(JobStage).where(
                JobStage.job_id == job.id,
                JobStage.stage == JobStageName.PREPROCESSING.value,
            )
        )
    ).scalar_one()
    assert stage.status == StageStatus.FAILED.value
    assert stage.error_detail is not None
    assert "ASR produced no segments" in stage.error_detail
    worker._publisher.publish.assert_awaited()
    published = worker._publisher.publish.await_args.args[0]
    assert published.detail_type == "eventforge.pipeline.failed"
    assert "ASR produced no segments" in published.payload.error_message
