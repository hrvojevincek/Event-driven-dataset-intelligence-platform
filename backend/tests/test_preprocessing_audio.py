"""Preprocessing tests for audio assets with mocked ASR."""

import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import Settings
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
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import build_intake_completed_event
from eventforge.services.preprocessing.asr import Utterance
from eventforge.services.preprocessing.audio_segments import SpeakerRole
from eventforge.services.storage.local import LocalStorage
from eventforge.stages.preprocessing import run_preprocessing


@dataclass
class MockASR:
    """Deterministic ASR stub for preprocessing tests."""

    utterances: list[Utterance]
    model_name: str = "mock/test"

    def transcribe(self, path: Path) -> list[Utterance]:
        return self.utterances


class MockSpeakerRoleClassifier:
    """Deterministic speaker-role stub for preprocessing tests."""

    def __init__(self, roles: list[SpeakerRole]) -> None:
        self._roles = roles

    async def classify(
        self,
        utterances: list[Utterance],
        *,
        job_id: uuid.UUID,
    ) -> list[SpeakerRole]:
        if len(self._roles) != len(utterances):
            msg = "mock role count must match utterance count"
            raise ValueError(msg)
        return self._roles


@pytest.fixture
def upload_root(tmp_path: Path) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    return root


@pytest.fixture
def local_storage(upload_root: Path) -> LocalStorage:
    return LocalStorage(Settings(upload_root=str(upload_root)))


async def _seed_audio_project(
    db_session: AsyncSession,
    storage: LocalStorage,
) -> tuple[Job, list[Asset]]:
    suffix = uuid.uuid4().hex[:8]
    user = User(email=f"audio-{suffix}@example.com", auth_subject_id=f"audio-user-{suffix}")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id=f"corr-audio-{suffix}",
        name="Audio batch",
        schema_json={"type": "object"},
        schema_template="support_call_audio",
        domain="audio",
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    db_session.add(
        JobStage(
            job_id=job.id,
            stage=JobStageName.PREPROCESSING.value,
            status=StageStatus.PENDING.value,
        )
    )

    fixture = (
        Path(__file__).resolve().parents[2] / "fixtures" / "support-calls-audio" / "call_001.wav"
    )
    _, storage_uri = storage.save_bytes(job.id, "call_001.wav", fixture.read_bytes())
    asset = Asset(
        job_id=job.id,
        filename="call_001.wav",
        mime_type="audio/wav",
        storage_uri=storage_uri,
        byte_size=fixture.stat().st_size,
        fetch_status=AssetFetchStatus.OK.value,
    )
    db_session.add(asset)
    await db_session.flush()
    return job, [asset]


async def test_run_preprocessing_audio_writes_speaker_turn_segments(
    db_session: AsyncSession,
    local_storage: LocalStorage,
) -> None:
    job, assets = await _seed_audio_project(db_session, local_storage)
    mock_publisher = AsyncMock(spec=EventPublisher)
    mock_asr = MockASR(
        utterances=[
            Utterance("Customer called about a duplicate charge.", 0, 8_000, -0.21),
            Utterance("Agent offered a refund.", 8_000, 16_000, -0.15),
        ]
    )
    mock_roles = MockSpeakerRoleClassifier(["customer", "agent"])

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
        asr=mock_asr,
        role_classifier=mock_roles,
    )

    assert result is not None
    assert result.payload.segment_count == 2

    result = await db_session.execute(
        select(Segment).where(Segment.job_id == job.id).order_by(Segment.segment_index)
    )
    rows = result.scalars().all()
    assert len(rows) == 2
    assert rows[0].metadata_json is not None
    assert rows[0].metadata_json["kind"] == "audio_turn"
    assert rows[0].metadata_json["speaker"] == "customer"
    assert rows[0].start_offset == 0
    assert rows[0].end_offset == 8_000
    assert "duplicate charge" in rows[0].content
    assert rows[1].metadata_json["speaker"] == "agent"
    assert rows[1].start_offset == 8_000
    assert rows[1].end_offset == 16_000
    assert rows[1].metadata_json["asr_model"] == "mock/test"
    assert rows[1].metadata_json["asr_avg_logprob"] == -0.15


async def test_run_preprocessing_audio_fails_on_empty_transcript(
    db_session: AsyncSession,
    local_storage: LocalStorage,
) -> None:
    job, assets = await _seed_audio_project(db_session, local_storage)
    mock_publisher = AsyncMock(spec=EventPublisher)
    mock_asr = MockASR(utterances=[])

    inbound = build_intake_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        asset_ids=[asset.id for asset in assets],
    )

    with pytest.raises(ValueError, match="ASR produced no segments"):
        await run_preprocessing(
            db_session,
            mock_publisher,
            inbound,
            storage=local_storage,
            asr=mock_asr,
            role_classifier=MockSpeakerRoleClassifier([]),
        )
