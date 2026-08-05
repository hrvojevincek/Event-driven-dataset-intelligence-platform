from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.otel import traced_agent
from eventforge.db.models import AssetFetchStatus, JobStageName, JobStatus, StageStatus
from eventforge.db.repositories import (
    AssetRepository,
    JobRepository,
    JobStageRepository,
    ProcessedEventRepository,
)
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_INTAKE, EventPublisher, EventPublishError
from eventforge.events.schemas import (
    DETAIL_TYPE_INTAKE_COMPLETED,
    DETAIL_TYPE_PROJECT_SUBMITTED,
    WORKER_NAME_INTAKE,
    IntakeCompletedEvent,
    ProjectSubmittedEvent,
    build_intake_completed_event,
)
from eventforge.services.storage.local import LocalStorage, get_local_storage


async def _finalize_assets(
    session: AsyncSession,
    assets: list,
    storage: LocalStorage,
) -> list:
    """Mark assets OK when their storage URI resolves to a local file."""
    ready = []
    for asset in assets:
        if storage.exists(asset.storage_uri):
            asset.fetch_status = AssetFetchStatus.OK.value
            ready.append(asset)
        else:
            asset.fetch_status = AssetFetchStatus.FAILED.value
    await session.flush()
    if not ready:
        msg = "No uploaded assets found on disk for intake"
        raise ValueError(msg)
    return ready


@traced_agent(WORKER_NAME_INTAKE)
async def process_project_submitted(
    session: AsyncSession,
    publisher: EventPublisher,
    event: ProjectSubmittedEvent,
    *,
    storage: LocalStorage | None = None,
) -> IntakeCompletedEvent | None:
    """Run intake for one project.submitted event. Returns None if already processed."""
    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)

    if not await processed_repo.try_claim(event_id, WORKER_NAME_INTAKE):
        return None

    job_repo = JobRepository(session)
    stage_repo = JobStageRepository(session)
    asset_repo = AssetRepository(session)
    store = storage or get_local_storage()

    job = await job_repo.get_by_id(event.job_id)
    if job is None:
        msg = f"Job not found for intake: {event.job_id}"
        raise ValueError(msg)

    intake_stage = await stage_repo.get_by_job_and_stage(job.id, JobStageName.INTAKE.value)
    if intake_stage is None:
        msg = f"Intake stage missing for job: {job.id}"
        raise ValueError(msg)

    job.status = JobStatus.RUNNING.value
    if intake_stage.status != StageStatus.COMPLETED.value:
        await stage_repo.mark_running(intake_stage)

    assets = await asset_repo.list_by_job_id(job.id)
    if not assets:
        msg = f"No assets registered for job: {job.id}"
        raise ValueError(msg)

    ready_assets = await _finalize_assets(session, assets, store)

    completed_event = build_intake_completed_event(
        job_id=job.id,
        correlation_id=event.correlation_id,
        asset_ids=[asset.id for asset in ready_assets],
        event_id=deterministic_event_id(job.id, DETAIL_TYPE_INTAKE_COMPLETED),
    )

    await stage_repo.mark_completed(intake_stage)
    await session.commit()

    try:
        await publisher.publish(completed_event, source=EVENT_SOURCE_INTAKE)
    except EventPublishError:
        await processed_repo.release_claim(event_id, WORKER_NAME_INTAKE)
        await session.commit()
        raise

    return completed_event


def parse_project_submitted_event(detail: dict) -> ProjectSubmittedEvent:
    if detail.get("detail_type") != DETAIL_TYPE_PROJECT_SUBMITTED:
        msg = f"Unexpected detail_type: {detail.get('detail_type')}"
        raise ValueError(msg)
    return ProjectSubmittedEvent.model_validate(detail)
