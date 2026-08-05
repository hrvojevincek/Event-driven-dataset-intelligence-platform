from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.otel import traced_stage
from eventforge.db.models import AssetFetchStatus, JobStageName, JobStatus, StageStatus
from eventforge.db.repositories import AssetRepository
from eventforge.events.deterministic import deterministic_event_id
from eventforge.events.publisher import EVENT_SOURCE_INTAKE, EventPublisher
from eventforge.events.schemas import (
    DETAIL_TYPE_INTAKE_COMPLETED,
    DETAIL_TYPE_PROJECT_SUBMITTED,
    WORKER_NAME_INTAKE,
    IntakeCompletedEvent,
    ProjectSubmittedEvent,
    build_intake_completed_event,
)
from eventforge.services.storage.local import LocalStorage, get_local_storage
from eventforge.stages._runtime import StageRun, parse_event


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


@traced_stage(WORKER_NAME_INTAKE)
async def process_project_submitted(
    session: AsyncSession,
    publisher: EventPublisher,
    event: ProjectSubmittedEvent,
    *,
    storage: LocalStorage | None = None,
) -> IntakeCompletedEvent | None:
    """Run intake for one project.submitted event. Returns None if already processed."""
    run = await StageRun.begin(
        session,
        publisher,
        event,
        worker_name=WORKER_NAME_INTAKE,
        project_label="job",
    )
    if run is None:
        return None

    store = storage or get_local_storage()
    intake_stage = await run.require_stage(JobStageName.INTAKE)

    run.project.status = JobStatus.RUNNING.value
    if intake_stage.status != StageStatus.COMPLETED.value:
        await run.mark_running(intake_stage)

    assets = await AssetRepository(session).list_by_job_id(run.project.id)
    if not assets:
        msg = f"No assets registered for job: {run.project.id}"
        raise ValueError(msg)

    ready_assets = await _finalize_assets(session, assets, store)

    completed_event = build_intake_completed_event(
        job_id=run.project.id,
        correlation_id=event.correlation_id,
        asset_ids=[asset.id for asset in ready_assets],
        event_id=deterministic_event_id(run.project.id, DETAIL_TYPE_INTAKE_COMPLETED),
    )

    await run.complete_stage(intake_stage)
    await run.publish(completed_event, source=EVENT_SOURCE_INTAKE)
    return completed_event


def parse_project_submitted_event(detail: dict) -> ProjectSubmittedEvent:
    return parse_event(detail, DETAIL_TYPE_PROJECT_SUBMITTED, ProjectSubmittedEvent)
