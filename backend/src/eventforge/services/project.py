"""Submit dataset projects with file uploads."""

import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.core.config import get_settings
from eventforge.core.otel import agent_span
from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    Asset,
    AssetFetchStatus,
    Job,
    JobStage,
    JobStatus,
    StageStatus,
    User,
)
from eventforge.db.repositories import ProcessedEventRepository
from eventforge.events.publisher import PUBLISHER_WORKER_NAME, EventPublisher
from eventforge.events.schemas import build_project_submitted_event
from eventforge.services.intake import resolve_schema, validate_upload
from eventforge.services.storage.local import LocalStorage, get_local_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitProjectResult:
    """Identifiers returned after a project is submitted and persisted."""

    job_id: uuid.UUID
    correlation_id: str
    asset_count: int


@dataclass(frozen=True)
class UploadPayload:
    """One uploaded file passed from the API layer."""

    filename: str
    content: bytes


async def submit_project(
    session: AsyncSession,
    publisher: EventPublisher,
    user: User,
    *,
    name: str,
    uploads: list[UploadPayload],
    schema_template: str | None = None,
    schema_json: dict | None = None,
    domain: str = "documents",
    storage: LocalStorage | None = None,
    max_upload_file_bytes: int | None = None,
    max_upload_files: int | None = None,
) -> SubmitProjectResult:
    """Persist project metadata, store uploads locally, and emit project.submitted."""
    if not uploads:
        msg = "At least one file is required"
        raise ValueError(msg)

    store = storage or get_local_storage()
    app_settings = get_settings()
    max_files = max_upload_files or app_settings.max_upload_files_per_project
    max_bytes = max_upload_file_bytes or app_settings.max_upload_file_bytes
    if len(uploads) > max_files:
        msg = f"Too many files (max {max_files})"
        raise ValueError(msg)

    resolved_schema, template_id = resolve_schema(
        schema_template=schema_template,
        schema_json=schema_json,
    )

    job_id = uuid.uuid4()
    correlation_id = uuid.uuid4().hex

    job = Job(
        id=job_id,
        user_id=user.id,
        correlation_id=correlation_id,
        name=name,
        description=None,
        schema_json=json.dumps(resolved_schema),
        schema_template=template_id,
        domain=domain,
        status=JobStatus.PENDING.value,
    )
    session.add(job)

    for stage_name in PIPELINE_STAGE_NAMES:
        session.add(
            JobStage(
                job_id=job_id,
                stage=stage_name.value,
                status=StageStatus.PENDING.value,
            )
        )

    assets: list[Asset] = []
    for upload in uploads:
        validated = validate_upload(
            upload.filename,
            upload.content,
            max_bytes=max_bytes,
        )
        _, storage_uri = store.save_bytes(job_id, validated.filename, upload.content)
        asset = Asset(
            job_id=job_id,
            filename=validated.filename,
            mime_type=validated.mime_type,
            storage_uri=storage_uri,
            byte_size=validated.byte_size,
            provenance=validated.provenance_json,
            fetch_status=AssetFetchStatus.PENDING.value,
        )
        session.add(asset)
        assets.append(asset)

    await session.flush()

    event = build_project_submitted_event(
        job_id=job_id,
        correlation_id=correlation_id,
        name=name,
        schema_json=resolved_schema,
        schema_template=template_id,
        domain=domain,
        asset_count=len(assets),
    )

    processed_repo = ProcessedEventRepository(session)
    event_id = str(event.event_id)
    if await processed_repo.try_claim(event_id, PUBLISHER_WORKER_NAME):
        with agent_span(
            "api",
            "submit_project",
            correlation_id=correlation_id,
            job_id=str(job_id),
            event_id=event_id,
        ):
            await publisher.publish_project_submitted(event)
    else:
        logger.info(
            "Skipped publish; project.submitted already claimed",
            extra={
                "event_id": event_id,
                "job_id": str(job_id),
                "correlation_id": correlation_id,
            },
        )

    await session.commit()
    return SubmitProjectResult(
        job_id=job_id,
        correlation_id=correlation_id,
        asset_count=len(assets),
    )
