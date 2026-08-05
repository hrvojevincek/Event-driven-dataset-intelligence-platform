import json
import uuid

import pytest

from eventforge.db.models import Job, Segment
from eventforge.services.intake.templates import (
    DOCUMENT_CLASSIFICATION_TEMPLATE,
    SUPPORT_CALL_TEMPLATE,
)
from eventforge.services.planning.schema_templates import (
    load_label_schema,
    segments_per_task_for_template,
    validate_label_schema,
)
from eventforge.services.planning.task_builder import build_annotation_tasks


def test_validate_label_schema_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="type 'object'"):
        validate_label_schema({"type": "array"}, SUPPORT_CALL_TEMPLATE)


def test_validate_label_schema_requires_template_fields() -> None:
    schema = {
        "type": "object",
        "properties": {"emotion": {"type": "string"}},
        "required": ["emotion"],
    }
    with pytest.raises(ValueError, match="template field 'intent'"):
        validate_label_schema(schema, SUPPORT_CALL_TEMPLATE)


def test_load_label_schema_parses_project_schema() -> None:
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
    loaded = load_label_schema(json.dumps(schema), SUPPORT_CALL_TEMPLATE)
    assert loaded["properties"]["topic"]["type"] == "string"


def test_segments_per_task_defaults_by_template() -> None:
    assert segments_per_task_for_template(SUPPORT_CALL_TEMPLATE) == 1
    assert segments_per_task_for_template(DOCUMENT_CLASSIFICATION_TEMPLATE) == 5


def test_build_annotation_tasks_batches_support_call_segments_one_per_task() -> None:
    job = Job(
        user_id=uuid.uuid4(),
        correlation_id="corr-planning",
        name="Support batch",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=json.dumps(
            {
                "type": "object",
                "properties": {
                    "emotion": {"type": "string"},
                    "intent": {"type": "string"},
                    "topic": {"type": "string"},
                    "resolution_status": {"type": "string"},
                },
                "required": ["emotion", "intent", "topic", "resolution_status"],
            }
        ),
    )
    asset_id = uuid.uuid4()
    segments = [
        Segment(
            job_id=job.id,
            asset_id=asset_id,
            segment_index=index,
            content=f"Segment {index}",
        )
        for index in range(3)
    ]

    planned = build_annotation_tasks(job, segments)

    assert len(planned) == 3
    assert planned[0].task_index == 0
    assert len(planned[0].segment_ids) == 1
    assert "support-call segment" in planned[0].instructions
    payload = json.loads(planned[0].segment_ids_json)
    assert payload["schema_template"] == SUPPORT_CALL_TEMPLATE
    assert payload["label_schema"]["required"] == [
        "emotion",
        "intent",
        "topic",
        "resolution_status",
    ]


def test_build_annotation_tasks_batches_document_segments() -> None:
    job = Job(
        user_id=uuid.uuid4(),
        correlation_id="corr-docs",
        name="Docs batch",
        schema_template=DOCUMENT_CLASSIFICATION_TEMPLATE,
        schema_json=json.dumps(
            {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "summary": {"type": "string"},
                    "sensitivity_flag": {"type": "string"},
                },
                "required": ["category", "summary", "sensitivity_flag"],
            }
        ),
    )
    asset_id = uuid.uuid4()
    segments = [
        Segment(
            job_id=job.id,
            asset_id=asset_id,
            segment_index=index,
            content=f"Paragraph {index}",
        )
        for index in range(7)
    ]

    planned = build_annotation_tasks(job, segments)

    assert len(planned) == 2
    assert len(planned[0].segment_ids) == 5
    assert len(planned[1].segment_ids) == 2
    assert "Classify each document segment" in planned[0].instructions
