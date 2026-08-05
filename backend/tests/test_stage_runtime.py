import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from eventforge.events.publisher import EventPublishError
from eventforge.stages._runtime import StageRun, parse_event


class _FakeEvent:
    def __init__(self) -> None:
        self.event_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.correlation_id = "corr-test"


@pytest.mark.asyncio
async def test_begin_returns_none_when_claim_fails() -> None:
    session = AsyncMock()
    event = _FakeEvent()
    processed_repo = AsyncMock()
    processed_repo.try_claim = AsyncMock(return_value=False)

    with patch(
        "eventforge.stages._runtime.ProcessedEventRepository",
        return_value=processed_repo,
    ):
        result = await StageRun.begin(
            session,
            AsyncMock(),
            event,
            worker_name="intake",
        )

    assert result is None


@pytest.mark.asyncio
async def test_begin_raises_when_project_missing() -> None:
    session = AsyncMock()
    event = _FakeEvent()
    processed_repo = AsyncMock()
    processed_repo.try_claim = AsyncMock(return_value=True)
    job_repo = AsyncMock()
    job_repo.get_by_id = AsyncMock(return_value=None)

    with patch(
        "eventforge.stages._runtime.ProcessedEventRepository",
        return_value=processed_repo,
    ):
        with pytest.raises(ValueError, match="Project not found"):
            await StageRun.begin(
                session,
                AsyncMock(),
                event,
                worker_name="planning",
                job_repo=job_repo,
            )


@pytest.mark.asyncio
async def test_publish_releases_claim_on_failure() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    publisher = AsyncMock()
    publisher.publish = AsyncMock(side_effect=EventPublishError("boom"))
    processed_repo = AsyncMock()
    processed_repo.release_claim = AsyncMock()
    project = MagicMock()
    project.id = uuid.uuid4()

    run = StageRun(
        session=session,
        publisher=publisher,
        processed_repo=processed_repo,
        stage_repo=AsyncMock(),
        worker_name="export",
        event_id="evt-1",
        project=project,
    )

    with pytest.raises(EventPublishError):
        await run.publish(MagicMock(), source="eventforge.workers.export")

    processed_repo.release_claim.assert_awaited_once_with("evt-1", "export")
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_defer_releases_claim_and_commits() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    processed_repo = AsyncMock()
    processed_repo.release_claim = AsyncMock()

    run = StageRun(
        session=session,
        publisher=None,
        processed_repo=processed_repo,
        stage_repo=AsyncMock(),
        worker_name="export",
        event_id="evt-2",
        project=MagicMock(),
    )

    await run.defer()

    processed_repo.release_claim.assert_awaited_once_with("evt-2", "export")
    session.commit.assert_awaited_once()


def test_parse_event_validates_detail_type() -> None:
    class SampleEvent(BaseModel):
        detail_type: str
        value: int

    event = parse_event(
        {"detail_type": "eventforge.sample", "value": 1},
        "eventforge.sample",
        SampleEvent,
    )
    assert event.value == 1

    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_event({"detail_type": "other"}, "eventforge.sample", SampleEvent)
