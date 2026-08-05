import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from eventforge.db.models import (
    PIPELINE_STAGE_NAMES,
    AnnotationBatch,
    AnnotationTask,
    Asset,
    AssetFetchStatus,
    DatasetExport,
    Job,
    JobStageName,
    JobStatus,
    Segment,
    User,
)
from eventforge.db.repositories import (
    AnnotationBatchRepository,
    AnnotationTaskRepository,
    AssetRepository,
    DatasetExportRepository,
    JobRepository,
    SegmentRepository,
)


@pytest.mark.asyncio
async def test_project_model_and_pipeline_stages(db_session: AsyncSession) -> None:
    user = User(email="project@example.com", auth_subject_id="user_project")
    db_session.add(user)
    await db_session.flush()

    schema = json.dumps({"fields": [{"name": "topic", "type": "enum", "values": ["billing"]}]})
    job = Job(
        user_id=user.id,
        correlation_id="corr-project-001",
        name="Support call batch",
        description="Demo fixture",
        schema_json=schema,
        schema_template="support_call",
        domain="documents",
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()

    fetched = await JobRepository(db_session).get_by_correlation_id("corr-project-001")
    assert fetched is not None
    assert fetched.name == "Support call batch"
    assert fetched.schema_template == "support_call"
    assert len(PIPELINE_STAGE_NAMES) == 5
    assert PIPELINE_STAGE_NAMES[0] == JobStageName.INTAKE


@pytest.mark.asyncio
async def test_asset_segment_task_batch_export_repositories(db_session: AsyncSession) -> None:
    user = User(email="asset@example.com", auth_subject_id="user_asset")
    db_session.add(user)
    await db_session.flush()

    job = Job(
        user_id=user.id,
        correlation_id="corr-asset-001",
        name="Label run",
        schema_json="{}",
        status=JobStatus.RUNNING.value,
    )
    db_session.add(job)
    await db_session.flush()

    asset = Asset(
        job_id=job.id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///data/uploads/call_001.txt",
        byte_size=128,
        fetch_status=AssetFetchStatus.OK.value,
    )
    db_session.add(asset)
    await db_session.flush()

    segment = Segment(
        job_id=job.id,
        asset_id=asset.id,
        segment_index=0,
        content="Customer asked about a duplicate charge.",
        start_offset=0,
        end_offset=42,
    )
    db_session.add(segment)
    await db_session.flush()

    task = AnnotationTask(
        job_id=job.id,
        task_index=0,
        instructions="Label sentiment and topic.",
        segment_ids_json=json.dumps([str(segment.id)]),
    )
    db_session.add(task)
    await db_session.flush()

    task_id = uuid.uuid4()
    batch = AnnotationBatch(
        job_id=job.id,
        task_id=task_id,
        task_index=0,
        labels_json=json.dumps(
            {str(segment.id): {"topic": "billing", "sentiment": "negative"}}
        ),
        segment_count=1,
        confidence=Decimal("0.9100"),
    )
    db_session.add(batch)

    export = DatasetExport(
        job_id=job.id,
        export_content='{"segment_id": "..."}\n',
        qc_report_json=json.dumps({"coverage_pct": 100.0}),
    )
    db_session.add(export)
    await db_session.flush()

    assets = await AssetRepository(db_session).list_by_job_id(job.id)
    assert len(assets) == 1
    assert assets[0].filename == "call_001.txt"

    segments = await SegmentRepository(db_session).list_by_job_id(job.id)
    assert len(segments) == 1
    assert segments[0].content.startswith("Customer")

    tasks = await AnnotationTaskRepository(db_session).list_by_job_id(job.id)
    assert len(tasks) == 1
    assert tasks[0].task_index == 0

    batches = await AnnotationBatchRepository(db_session).list_by_job_id(job.id)
    assert len(batches) == 1
    assert batches[0].task_id == task_id

    stored_export = await DatasetExportRepository(db_session).get_by_job_id(job.id)
    assert stored_export is not None
    assert stored_export.qc_report_json.startswith("{")
