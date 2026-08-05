import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

from eventforge.db.models import Segment
from eventforge.services.annotation.labeler import (
    build_labels_json,
    decode_task_payload,
    label_segments,
)
from eventforge.services.intake.templates import SUPPORT_CALL_TEMPLATE
from eventforge.services.llm.client import LLMClient
from eventforge.services.llm.types import LLMCompletionResult


def _support_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "emotion": {"type": "string"},
            "intent": {"type": "string"},
            "topic": {"type": "string"},
            "resolution_status": {"type": "string"},
        },
        "required": ["emotion", "intent", "topic", "resolution_status"],
    }


def test_decode_task_payload_reads_planning_encoding() -> None:
    segment_ids = [uuid.uuid4(), uuid.uuid4()]
    encoded = json.dumps(
        {
            "segment_ids": [str(segment_id) for segment_id in segment_ids],
            "label_schema": _support_schema(),
            "schema_template": SUPPORT_CALL_TEMPLATE,
        }
    )

    decoded_ids, schema, template = decode_task_payload(encoded)

    assert decoded_ids == segment_ids
    assert schema["required"] == ["emotion", "intent", "topic", "resolution_status"]
    assert template == SUPPORT_CALL_TEMPLATE


def test_build_labels_json_serializes_segments() -> None:
    from eventforge.services.annotation.labeler import SegmentLabels

    segment_id = uuid.uuid4()
    payload = build_labels_json(
        [
            SegmentLabels(
                segment_id=segment_id,
                labels={
                    "emotion": "frustrated",
                    "intent": "complaint",
                    "topic": "billing",
                    "resolution_status": "unresolved",
                },
                confidence=Decimal("0.9100"),
            )
        ]
    )
    parsed = json.loads(payload)
    assert parsed["segments"][0]["segment_id"] == str(segment_id)
    assert parsed["segments"][0]["labels"]["topic"] == "billing"


async def test_label_segments_parses_llm_json() -> None:
    segment = Segment(
        job_id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        segment_index=0,
        content="Customer is upset about a duplicate charge.",
    )
    llm = AsyncMock(spec=LLMClient)
    llm.complete = AsyncMock(
        return_value=LLMCompletionResult(
            content=json.dumps(
                {
                    "segments": [
                        {
                            "segment_index": 0,
                            "labels": {
                                "emotion": "frustrated",
                                "intent": "complaint",
                                "topic": "billing",
                                "resolution_status": "unresolved",
                            },
                            "confidence": 0.92,
                        }
                    ]
                }
            ),
            model="gpt-4o-mini",
            input_tokens=10,
            output_tokens=20,
            cost_usd=Decimal("0.001"),
        )
    )

    result = await label_segments(
        llm,
        project_id=segment.job_id,
        instructions="Label each support-call segment.",
        segments=[segment],
        label_schema=_support_schema(),
    )

    assert result.segment_labels[0].labels["emotion"] == "frustrated"
    assert result.confidence == Decimal("0.9200")
    assert result.low_confidence is False


async def test_label_segments_falls_back_on_bad_json() -> None:
    segment = Segment(
        job_id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        segment_index=0,
        content="Hello",
    )
    llm = AsyncMock(spec=LLMClient)
    llm.complete = AsyncMock(
        return_value=LLMCompletionResult(
            content="not-json",
            model="gpt-4o-mini",
            input_tokens=5,
            output_tokens=5,
            cost_usd=Decimal("0.001"),
        )
    )

    result = await label_segments(
        llm,
        project_id=segment.job_id,
        instructions="Label each support-call segment.",
        segments=[segment],
        label_schema=_support_schema(),
    )

    assert result.segment_labels[0].labels["emotion"] == "unknown"
    assert result.low_confidence is True
