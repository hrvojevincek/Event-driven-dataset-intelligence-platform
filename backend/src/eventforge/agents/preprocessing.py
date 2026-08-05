import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_agent
from eventforge.db.models import Asset, JobStageName, Segment
from eventforge.db.repositories import (
    AssetRepository,
    JobRepository,
    JobStageRepository,
    ProcessedEventRepository,
    SegmentRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import (
    EVENT_SOURCE_PREPROCESSING,
    EventPublisher,
    EventPublishError,
)
from eventforge.events.schemas import (
    DETAIL_TYPE_INTAKE_COMPLETED,
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    WORKER_NAME_PREPROCESSING,
    IntakeCompletedEvent,
    PreprocessingCompletedEvent,
    build_preprocessing_completed_event,
)
from eventforge.services.preprocessing import read_asset_text, segment_text, source_kind_for_asset
from eventforge.services.storage.local import LocalStorage, get_local_storage


async def _load_or_create_segments(
    session: AsyncSession,
    job_id: uuid.UUID,
    assets: list[Asset],
    storage: LocalStorage,
    *,
    chunk_size: int,
    overlap: int,
) -> list[Segment]:
    segment_repo = SegmentRepository(session)
    existing = await segment_repo.list_by_job_id(job_id)
    if existing:
        return existing

    segments: list[Segment] = []
    for asset in assets:
        text = read_asset_text(asset, storage)
        kind = source_kind_for_asset(asset)
        for piece in segment_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
            source_kind=kind,
        ):
            segments.append(
                Segment(
                    job_id=job_id,
                    asset_id=asset.id,
                    segment_index=piece.segment_index,
                    content=piece.content,
                    start_offset=piece.start_offset,
                    end_offset=piece.end_offset,
                )
            )

    if not segments:
        msg = "No segmentable content found in assets"
        raise ValueError(msg)

    session.add_all(segments)
    await session.flush()
    return segments


@traced_agent(WORKER_NAME_PREPROCESSING)
async def process_intake_completed(
    session: AsyncSession,
    publisher: EventPublisher,
    event: IntakeCompletedEvent,
    *,
    storage: LocalStorage | None = None,
) -> PreprocessingCompletedEvent | None:
    """Run preprocessing for one intake.completed event. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_PREPROCESSING):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)
    asset_repo = AssetRepository(session)
    store = storage or get_local_storage()

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for preprocessing: {event.job_id}"
        raise ValueError(msg)

    preprocessing_stage = await stage_repo.get_by_job_and_stage(
        job.id,
        JobStageName.PREPROCESSING.value,
    )
    if preprocessing_stage is None:
        msg = f"Preprocessing stage missing for job: {job.id}"
        raise ValueError(msg)

    assets = await asset_repo.list_by_ids(event.payload.asset_ids)
    if len(assets) != len(event.payload.asset_ids):
        msg = f"Assets missing for preprocessing job: {event.job_id}"
        raise ValueError(msg)

    settings = get_settings()
    await stage_repo.mark_running(preprocessing_stage)
    segments = await _load_or_create_segments(
        session,
        job.id,
        assets,
        store,
        chunk_size=settings.preprocessing_segment_size_tokens,
        overlap=settings.preprocessing_segment_overlap_tokens,
    )

    completed_event = build_preprocessing_completed_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        segment_ids=[segment.id for segment in segments],
        event_id=deterministic_event_id(job.id, DETAIL_TYPE_PREPROCESSING_COMPLETED),
    )

    await stage_repo.mark_completed(preprocessing_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_PREPROCESSING)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_PREPROCESSING)
        await session.commit()
        raise

    return completed_event


def parse_intake_completed_event(detail: dict) -> IntakeCompletedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_INTAKE_COMPLETED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return IntakeCompletedEvent.model_validate(detail)
