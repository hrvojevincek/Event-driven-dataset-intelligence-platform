"""Preprocessing stage: turn uploaded assets into annotatable segments.

Consumes ``intake.completed``, loads each asset from local storage, extracts text
(plain/Markdown/PDF via PyMuPDF), splits into token-bounded chunks with overlap,
persists ``Segment`` rows (idempotent per job), and publishes
``preprocessing.completed`` with segment IDs for the planning stage.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import traced_stage
from eventforge.db.models import Asset, JobStageName, Segment
from eventforge.db.repositories import AssetRepository, SegmentRepository
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_PREPROCESSING, EventPublisher
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
from eventforge.stages._runtime import StageRun, parse_event


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


@traced_stage(WORKER_NAME_PREPROCESSING)
async def run_preprocessing(
    session: AsyncSession,
    publisher: EventPublisher,
    event: IntakeCompletedEvent,
    *,
    storage: LocalStorage | None = None,
) -> PreprocessingCompletedEvent | None:
    """Run preprocessing for one intake.completed event. Returns None if already processed."""
    run = await StageRun.begin(
        session,
        publisher,
        event,
        worker_name=WORKER_NAME_PREPROCESSING,
    )
    if run is None:
        return None

    store = storage or get_local_storage()
    preprocessing_stage = await run.require_stage(JobStageName.PREPROCESSING)

    assets = await AssetRepository(session).list_by_ids(event.payload.asset_ids)
    if len(assets) != len(event.payload.asset_ids):
        msg = f"Assets missing for preprocessing job: {event.job_id}"
        raise ValueError(msg)

    settings = get_settings()
    await run.mark_running(preprocessing_stage)
    segments = await _load_or_create_segments(
        session,
        run.job.id,
        assets,
        store,
        chunk_size=settings.preprocessing_segment_size_tokens,
        overlap=settings.preprocessing_segment_overlap_tokens,
    )

    completed_event = build_preprocessing_completed_event(
        job_id=run.job.id,
        correlation_id=event.correlation_id,
        segment_ids=[segment.id for segment in segments],
        event_id=deterministic_event_id(run.job.id, DETAIL_TYPE_PREPROCESSING_COMPLETED),
    )

    await run.complete_stage(preprocessing_stage)
    await run.publish(completed_event, source=EVENT_SOURCE_PREPROCESSING)
    return completed_event


def parse_intake_completed_event(detail: dict) -> IntakeCompletedEvent:
    return parse_event(detail, DETAIL_TYPE_INTAKE_COMPLETED, IntakeCompletedEvent)
