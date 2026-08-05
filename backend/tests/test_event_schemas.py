import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from eventforge.events.schemas import (
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
    DETAIL_TYPE_EXPORT_COMPLETED,
    DETAIL_TYPE_INTAKE_COMPLETED,
    DETAIL_TYPE_PLANNING_COMPLETED,
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    DETAIL_TYPE_PROJECT_SUBMITTED,
    DETAIL_TYPE_QUERY_SUBMITTED,
    EXPORT_COMPLETED_SCHEMA_VERSION,
    INTAKE_COMPLETED_SCHEMA_VERSION,
    PLANNING_COMPLETED_SCHEMA_VERSION,
    PREPROCESSING_COMPLETED_SCHEMA_VERSION,
    PROJECT_SUBMITTED_SCHEMA_VERSION,
    QUERY_SUBMITTED_SCHEMA_VERSION,
    ProjectSubmittedEvent,
    QueryDepth,
    QuerySubmittedPayload,
    build_annotation_task_completed_event,
    build_export_completed_event,
    build_intake_completed_event,
    build_planning_completed_event,
    build_preprocessing_completed_event,
    build_project_submitted_event,
    build_query_submitted_event,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_EVENTS = REPO_ROOT / "shared" / "events"

JOB_ID = UUID("11111111-1111-4111-8111-111111111111")
EVENT_ID = UUID("22222222-2222-4222-8222-222222222222")
FIXED_TS = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)


def test_query_submitted_payload_requires_topic() -> None:
    with pytest.raises(ValidationError):
        QuerySubmittedPayload.model_validate({})


def test_query_submitted_payload_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        QuerySubmittedPayload.model_validate({"topic": "AI agents", "extra": True})


def test_build_query_submitted_event_sets_envelope_fields() -> None:
    event = build_query_submitted_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        topic="Event-driven architectures",
        depth=QueryDepth.DEEP,
        max_sources=10,
        event_id=EVENT_ID,
        timestamp=FIXED_TS,
    )

    assert event.detail_type == DETAIL_TYPE_QUERY_SUBMITTED
    assert event.schema_version == QUERY_SUBMITTED_SCHEMA_VERSION
    assert event.job_id == JOB_ID
    assert event.payload.topic == "Event-driven architectures"
    assert event.payload.depth == QueryDepth.DEEP
    assert event.payload.max_sources == 10


def test_build_project_submitted_event_sets_envelope_fields() -> None:
    schema = {"type": "object", "properties": {"emotion": {"type": "string"}}}
    event = build_project_submitted_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        name="Support calls batch 1",
        schema_json=schema,
        schema_template="support_call",
        domain="support_calls",
        asset_count=10,
        event_id=EVENT_ID,
        timestamp=FIXED_TS,
    )

    assert event.detail_type == DETAIL_TYPE_PROJECT_SUBMITTED
    assert event.schema_version == PROJECT_SUBMITTED_SCHEMA_VERSION
    assert event.payload.name == "Support calls batch 1"
    assert event.payload.output_schema == schema
    assert event.payload.schema_template == "support_call"
    assert event.payload.asset_count == 10


def test_build_intake_completed_event_sets_payload() -> None:
    asset_ids = [UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")]
    event = build_intake_completed_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        asset_ids=asset_ids,
        event_id=EVENT_ID,
        timestamp=FIXED_TS,
    )

    assert event.detail_type == DETAIL_TYPE_INTAKE_COMPLETED
    assert event.schema_version == INTAKE_COMPLETED_SCHEMA_VERSION
    assert event.payload.asset_ids == asset_ids
    assert event.payload.asset_count == 1


def test_build_preprocessing_completed_event_sets_payload() -> None:
    segment_ids = [UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")]
    event = build_preprocessing_completed_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        segment_ids=segment_ids,
    )

    assert event.detail_type == DETAIL_TYPE_PREPROCESSING_COMPLETED
    assert event.schema_version == PREPROCESSING_COMPLETED_SCHEMA_VERSION
    assert event.payload.segment_count == 1


def test_build_planning_completed_event_sets_payload() -> None:
    task_ids = [UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")]
    event = build_planning_completed_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        task_ids=task_ids,
    )

    assert event.detail_type == DETAIL_TYPE_PLANNING_COMPLETED
    assert event.schema_version == PLANNING_COMPLETED_SCHEMA_VERSION
    assert event.payload.task_count == 1


def test_build_annotation_task_completed_event_sets_payload() -> None:
    task_id = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    batch_id = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    event = build_annotation_task_completed_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        task_id=task_id,
        batch_id=batch_id,
        task_index=0,
    )

    assert event.detail_type == DETAIL_TYPE_ANNOTATION_TASK_COMPLETED
    assert event.payload.batch_id == batch_id


def test_build_export_completed_event_sets_payload() -> None:
    export_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    event = build_export_completed_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        export_id=export_id,
        batch_count=3,
        segment_count=12,
    )

    assert event.detail_type == DETAIL_TYPE_EXPORT_COMPLETED
    assert event.schema_version == EXPORT_COMPLETED_SCHEMA_VERSION
    assert event.payload.export_id == export_id
    assert event.payload.segment_count == 12


def test_project_submitted_event_serializes_to_json_compatible_dict() -> None:
    event = build_project_submitted_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        name="Test project",
        schema_json={"type": "object"},
    )

    data = json.loads(event.model_dump_json())
    assert data["detail_type"] == "eventforge.project.submitted"
    assert data["payload"]["name"] == "Test project"
    assert data["payload"]["domain"] == "documents"


def test_query_submitted_event_serializes_to_json_compatible_dict() -> None:
    event = build_query_submitted_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        topic="Test",
    )

    data = json.loads(event.model_dump_json())
    assert data["detail_type"] == "eventforge.query.submitted"
    assert data["payload"]["topic"] == "Test"
    assert data["payload"]["depth"] == "standard"


def test_round_trip_through_pydantic() -> None:
    original = build_project_submitted_event(
        job_id=JOB_ID,
        correlation_id="corr-abc",
        name="Round trip",
        schema_json={"fields": []},
    )

    restored = ProjectSubmittedEvent.model_validate_json(original.model_dump_json())
    assert restored == original


@pytest.mark.parametrize(
    "filename",
    [
        "envelope.schema.json",
        "project.submitted.schema.json",
        "intake.completed.schema.json",
        "preprocessing.completed.schema.json",
        "planning.completed.schema.json",
        "annotation.task.dispatched.schema.json",
        "annotation.task.completed.schema.json",
        "annotation.all_completed.schema.json",
        "export.completed.schema.json",
        "pipeline.failed.schema.json",
        # Legacy schemas kept until Phase 7 cleanup
        "query.submitted.schema.json",
        "ingestion.completed.schema.json",
        "embedding.completed.schema.json",
    ],
)
def test_json_schema_files_are_valid_json(filename: str) -> None:
    path = SHARED_EVENTS / filename
    assert path.exists(), f"missing schema file: {path}"
    json.loads(path.read_text())
