import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import Settings, get_settings
from eventforge.db.models import (
    Asset,
    AssetFetchStatus,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    Segment,
    StageStatus,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    WORKER_NAME_PREPROCESSING,
    build_intake_completed_event,
    build_preprocessing_completed_event,
)
from eventforge.services.storage.local import LocalStorage
from eventforge.stages.preprocessing import parse_intake_completed_event, run_preprocessing
from eventforge.workers.preprocessing import PreprocessingWorker

settings = get_settings()


@pytest.fixture
def upload_root(tmp_path: Path) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    return root


@pytest.fixture
def local_storage(upload_root: Path) -> LocalStorage:
    test_settings = Settings(upload_root=str(upload_root))
    return LocalStorage(test_settings)


async def _seed_project_with_assets(
    db_session: AsyncSession,
    storage: LocalStorage,
    *,
    file_count: int = 2,
) -> tuple[Job, JobStage, list[Asset]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"preprocess-{suffix}@example.com", auth_subject_id=f"preprocess-user-{suffix}"
    )
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-preprocess-{suffix}",
        name="Support calls batch",
        schema_json={"type": "object"},
        schema_template="support_call",
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    stage = JobStage(
        job_id=job.id,
        stage=JobStageName.PREPROCESSING.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(stage)

    assets: list[Asset] = []
    for index in range(file_count):
        content = f"Paragraph one for call {index}.\n\nParagraph two for call {index}.\n".encode()
        _, storage_uri = storage.save_bytes(job.id, f"call_{index:03d}.txt", content)
        asset = Asset(
            job_id=job.id,
            filename=f"call_{index:03d}.txt",
            mime_type="text/plain",
            storage_uri=storage_uri,
            byte_size=len(content),
            fetch_status=AssetFetchStatus.OK.value,
        )
        db_session.add(asset)
        assets.append(asset)

    await db_session.flush()
    return job, stage, assets


def test_parse_intake_completed_event_rejects_wrong_type() -> None:
    with pytest.raises(ValueError, match="Unexpected detail_type"):
        parse_intake_completed_event({"detail_type": "eventforge.project.submitted"})


async def test_run_preprocessing_writes_segments_and_updates_stage(
    db_session: AsyncSession,
    local_storage: LocalStorage,
) -> None:
    job, stage, assets = await _seed_project_with_assets(db_session, local_storage)
    mock_publisher = AsyncMock(spec=EventPublisher)

    inbound = build_intake_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        asset_ids=[asset.id for asset in assets],
    )

    result = await run_preprocessing(
        db_session,
        mock_publisher,
        inbound,
        storage=local_storage,
    )

    assert result is not None
    assert result.detail_type == DETAIL_TYPE_PREPROCESSING_COMPLETED
    assert result.payload.segment_count >= len(assets)
    mock_publisher.publish.assert_awaited_once()

    await db_session.refresh(stage)
    assert stage.status == StageStatus.COMPLETED.value
    assert stage.completed_at is not None

    segment_count = await db_session.scalar(
        select(func.count()).select_from(Segment).where(Segment.job_id == job.id)
    )
    assert segment_count == result.payload.segment_count

    processed = ProcessedEventRepository(db_session)
    record = await processed.get_by_event_id(str(inbound.event_id))
    assert record is not None
    assert record.worker_name == WORKER_NAME_PREPROCESSING


async def test_run_preprocessing_skips_duplicate_event(
    db_session: AsyncSession,
    local_storage: LocalStorage,
) -> None:
    job, _, assets = await _seed_project_with_assets(db_session, local_storage, file_count=1)
    mock_publisher = AsyncMock(spec=EventPublisher)
    inbound = build_intake_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        asset_ids=[asset.id for asset in assets],
    )

    await run_preprocessing(
        db_session,
        mock_publisher,
        inbound,
        storage=local_storage,
    )
    mock_publisher.reset_mock()

    duplicate_result = await run_preprocessing(
        db_session,
        mock_publisher,
        inbound,
        storage=local_storage,
    )
    assert duplicate_result is None
    mock_publisher.publish.assert_not_awaited()

    segment_count = await db_session.scalar(
        select(func.count()).select_from(Segment).where(Segment.job_id == job.id)
    )
    assert segment_count >= 1


async def test_preprocessing_worker_deletes_message_on_success() -> None:
    worker = PreprocessingWorker()
    worker._delete_message = MagicMock()
    mock_client = MagicMock()

    event = build_intake_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-worker",
        asset_ids=[UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")],
    )
    body = json.dumps({"detail": json.loads(event.model_dump_json())})
    mock_client.receive_message.return_value = {
        "Messages": [{"ReceiptHandle": "rh-1", "Body": body, "MessageId": "m-1"}]
    }
    worker._client = mock_client
    worker._queue_url = "http://localstack/000000000000/eventforge-preprocessing"

    with patch.object(worker, "handle_message", new=AsyncMock()):
        handled = await worker.poll_once()

    assert handled == 1
    worker._delete_message.assert_called_once_with("rh-1")


def test_build_preprocessing_completed_event_sets_payload() -> None:
    segment_ids = [
        UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    ]
    event = build_preprocessing_completed_event(
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        correlation_id="corr-out",
        segment_ids=segment_ids,
    )
    assert event.detail_type == DETAIL_TYPE_PREPROCESSING_COMPLETED
    assert event.payload.segment_count == 2
    assert event.payload.segment_ids == segment_ids
