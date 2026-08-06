import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import (
    AnnotationBatch,
    AnnotationTask,
    AnnotationTaskSegment,
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
from eventforge.db.repositories import DatasetExportRepository, ProcessedEventRepository
from eventforge.events.publisher import EventPublisher
from eventforge.events.schemas import (
    WORKER_NAME_EXPORT,
    build_annotation_all_completed_event,
)
from eventforge.services.intake.templates import SUPPORT_CALL_TEMPLATE
from eventforge.stages.export import run_export
from eventforge.workers.export import ExportWorker


async def _seed_export_project(
    db_session: AsyncSession,
) -> tuple[Job, JobStage, AnnotationTask, Segment]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"export-{suffix}@example.com",
        auth_subject_id=f"export-user-{suffix}",
    )
    db_session.add(user)
    await db_session.flush()

    schema = {
        "type": "object",
        "properties": {
            "emotion": {"type": "string"},
            "intent": {"type": "string"},
            "topic": {"type": "string"},
            "resolution_status": {"type": "string"},
        },
        "required": ["emotion", "intent", "topic", "resolution_status"],
    }
    job = Job(
        user_id=user.id,
        correlation_id=f"corr-export-{suffix}",
        name="Support calls export",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=schema,
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    export_stage = JobStage(
        job_id=job.id,
        stage=JobStageName.EXPORT.value,
        status=StageStatus.PENDING.value,
    )
    db_session.add(export_stage)

    asset = Asset(
        job_id=job.id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///tmp/call_001.txt",
        fetch_status=AssetFetchStatus.OK.value,
    )
    db_session.add(asset)
    await db_session.flush()

    segment = Segment(
        job_id=job.id,
        asset_id=asset.id,
        segment_index=0,
        content="Customer asked about a duplicate charge.",
    )
    db_session.add(segment)
    await db_session.flush()

    task = AnnotationTask(
        job_id=job.id,
        task_index=0,
        instructions="Label support call segments.",
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(
        AnnotationTaskSegment(task_id=task.id, segment_id=segment.id, position=0)
    )

    batch = AnnotationBatch(
        job_id=job.id,
        task_id=task.id,
        task_index=0,
        labels_json={
            str(segment.id): {
                "emotion": "frustrated",
                "intent": "complaint",
                "topic": "billing",
                "resolution_status": "unresolved",
            },
        },
        segment_count=1,
        confidence=Decimal("0.8800"),
    )
    db_session.add(batch)
    await db_session.flush()
    return job, export_stage, task, segment


@pytest.mark.asyncio
async def test_run_export_persists_export(
    db_session: AsyncSession,
) -> None:
    job, export_stage, _task, segment = await _seed_export_project(db_session)
    publisher = AsyncMock(spec=EventPublisher)
    event = build_annotation_all_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_count=1,
    )

    result = await run_export(db_session, publisher, event)

    assert result is not None
    assert result.payload.batch_count == 1
    publisher.publish.assert_awaited_once()

    export = await DatasetExportRepository(db_session).get_by_job_id(job.id)
    assert export is not None
    line = json.loads(export.export_content.strip())
    assert line["segment_id"] == str(segment.id)
    assert line["labels"]["topic"] == "billing"

    qc = export.qc_report_json
    assert qc["coverage_pct"] == 100.0
    assert qc["batch_count"] == 1

    await db_session.refresh(job)
    await db_session.refresh(export_stage)
    assert job.status == JobStatus.COMPLETED.value
    assert export_stage.status == StageStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_run_export_is_idempotent(
    db_session: AsyncSession,
) -> None:
    job, _, _, _ = await _seed_export_project(db_session)
    publisher = AsyncMock(spec=EventPublisher)
    event = build_annotation_all_completed_event(
        job_id=job.id,
        correlation_id=job.correlation_id,
        task_count=1,
    )

    first = await run_export(db_session, publisher, event)
    second = await run_export(db_session, publisher, event)

    assert first is not None
    assert second is None
    publisher.publish.assert_awaited_once()

    claim = await ProcessedEventRepository(db_session).get_by_event_id(str(event.event_id))
    assert claim is not None
    assert claim.worker_name == WORKER_NAME_EXPORT


@pytest.mark.asyncio
async def test_export_worker_skips_annotation_task_completed() -> None:
    worker = ExportWorker()
    message = {
        "Body": json.dumps(
            {
                "detail-type": "eventforge.annotation.task.completed",
                "detail": {
                    "detail_type": "eventforge.annotation.task.completed",
                    "event_id": str(uuid.uuid4()),
                    "job_id": str(uuid.uuid4()),
                    "correlation_id": "corr",
                    "timestamp": "2026-08-05T12:00:00Z",
                    "schema_version": "1.0",
                    "payload": {
                        "task_id": str(uuid.uuid4()),
                        "batch_id": str(uuid.uuid4()),
                        "task_index": 0,
                    },
                },
            }
        )
    }

    await worker.handle_message(message)
