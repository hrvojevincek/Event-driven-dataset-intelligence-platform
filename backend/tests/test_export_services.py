import json
import uuid
from decimal import Decimal

import pytest

from eventforge.db.models import (
    AnnotationBatch,
    Asset,
    AssetFetchStatus,
    Job,
    JobStatus,
    Segment,
)
from eventforge.services.export.merge import merge_batches_to_jsonl
from eventforge.services.export.qc import build_qc_report
from eventforge.services.intake.templates import SUPPORT_CALL_TEMPLATE


@pytest.fixture
def support_schema() -> dict:
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


def test_merge_batches_to_jsonl_orders_segments_and_includes_provenance(
    support_schema: dict,
) -> None:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    segment_a = uuid.uuid4()
    segment_b = uuid.uuid4()

    project = Job(
        id=project_id,
        user_id=uuid.uuid4(),
        correlation_id="corr-export",
        name="Support calls",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=support_schema,
        status=JobStatus.RUNNING.value,
    )
    asset = Asset(
        id=asset_id,
        job_id=project_id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///tmp/call_001.txt",
        fetch_status=AssetFetchStatus.OK.value,
    )
    segments = [
        Segment(
            id=segment_b,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=1,
            content="Second segment",
        ),
        Segment(
            id=segment_a,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=0,
            content="First segment",
        ),
    ]
    batches = [
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=0,
            labels_json={
                "segments": [
                    {
                        "segment_id": str(segment_a),
                        "labels": {
                            "emotion": "frustrated",
                            "intent": "complaint",
                            "topic": "billing",
                            "resolution_status": "unresolved",
                        },
                        "confidence": 0.91,
                    }
                ]
            },
            segment_count=1,
            confidence=Decimal("0.9100"),
        ),
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=1,
            labels_json={
                "segments": [
                    {
                        "segment_id": str(segment_b),
                        "labels": {
                            "emotion": "neutral",
                            "intent": "question",
                            "topic": "shipping",
                            "resolution_status": "resolved",
                        },
                        "confidence": 0.42,
                    }
                ]
            },
            segment_count=1,
            confidence=Decimal("0.4200"),
        ),
    ]

    result = merge_batches_to_jsonl(
        project,
        batches,
        segments,
        {asset_id: asset},
    )

    assert result.segment_count == 2
    lines = [line for line in result.jsonl.splitlines() if line.strip()]
    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["content"] == "First segment"
    assert first["labels"]["topic"] == "billing"
    assert first["provenance"]["asset_filename"] == "call_001.txt"
    assert first["provenance"]["project_id"] == str(project_id)
    assert second["content"] == "Second segment"
    assert second["provenance"]["confidence"] == 0.42


def test_merge_batches_to_jsonl_uses_batch_confidence_for_canonical_labels_map(
    support_schema: dict,
) -> None:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    project = Job(
        id=project_id,
        user_id=uuid.uuid4(),
        correlation_id="corr-export-canonical",
        name="Support calls",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=support_schema,
        status=JobStatus.RUNNING.value,
    )
    asset = Asset(
        id=asset_id,
        job_id=project_id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///tmp/call_001.txt",
        fetch_status=AssetFetchStatus.OK.value,
    )
    segments = [
        Segment(
            id=segment_id,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=0,
            content="First segment",
        ),
    ]
    batches = [
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=0,
            labels_json={
                str(segment_id): {
                    "emotion": "frustrated",
                    "intent": "complaint",
                    "topic": "billing",
                    "resolution_status": "unresolved",
                }
            },
            segment_count=1,
            confidence=Decimal("0.8700"),
        ),
    ]

    result = merge_batches_to_jsonl(project, batches, segments, {asset_id: asset})

    record = json.loads(result.jsonl.splitlines()[0])
    assert record["provenance"]["confidence"] == 0.87


def test_merge_batches_to_jsonl_uses_annotator_model(support_schema: dict) -> None:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    project = Job(
        id=project_id,
        user_id=uuid.uuid4(),
        correlation_id="corr-export-annotator",
        name="Support calls",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=support_schema,
        status=JobStatus.RUNNING.value,
    )
    asset = Asset(
        id=asset_id,
        job_id=project_id,
        filename="call_001.txt",
        mime_type="text/plain",
        storage_uri="file:///tmp/call_001.txt",
        fetch_status=AssetFetchStatus.OK.value,
    )
    segments = [
        Segment(
            id=segment_id,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=0,
            content="First segment",
        ),
    ]
    batches = [
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=0,
            labels_json={
                str(segment_id): {
                    "emotion": "frustrated",
                    "intent": "complaint",
                    "topic": "billing",
                    "resolution_status": "unresolved",
                }
            },
            segment_count=1,
            confidence=Decimal("0.8700"),
        ),
    ]

    result = merge_batches_to_jsonl(
        project,
        batches,
        segments,
        {asset_id: asset},
        annotator="gpt-4o-mini",
    )

    record = json.loads(result.jsonl.splitlines()[0])
    assert record["provenance"]["annotator"] == "gpt-4o-mini"


def test_merge_batches_to_jsonl_includes_audio_fields_for_audio_project(
    support_schema: dict,
) -> None:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    project = Job(
        id=project_id,
        user_id=uuid.uuid4(),
        correlation_id="corr-export-audio",
        name="Audio calls",
        schema_template="support_call_audio",
        schema_json=support_schema,
        domain="audio",
        status=JobStatus.RUNNING.value,
    )
    asset = Asset(
        id=asset_id,
        job_id=project_id,
        filename="call_001.wav",
        mime_type="audio/wav",
        storage_uri="uploads/project/call_001.wav",
        fetch_status=AssetFetchStatus.OK.value,
    )
    segments = [
        Segment(
            id=segment_id,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=0,
            content="Customer asked about billing.",
            start_offset=0,
            end_offset=16_000,
            metadata_json={
                "kind": "audio_turn",
                "speaker": "customer",
                "asr_model": "mock/test",
                "asr_avg_logprob": -0.12,
            },
        ),
    ]
    batches = [
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=0,
            labels_json={
                str(segment_id): {
                    "emotion": "frustrated",
                    "intent": "complaint",
                    "topic": "billing",
                    "resolution_status": "unresolved",
                }
            },
            segment_count=1,
            confidence=Decimal("0.8700"),
        ),
    ]

    result = merge_batches_to_jsonl(project, batches, segments, {asset_id: asset})

    record = json.loads(result.jsonl.splitlines()[0])
    assert record["audio_uri"] == "uploads/project/call_001.wav"
    assert record["start_ms"] == 0
    assert record["end_ms"] == 16_000
    assert record["speaker"] == "customer"
    assert record["content"] == "Customer asked about billing."
    assert record["provenance"]["asr_model"] == "mock/test"
    assert record["provenance"]["asr_avg_logprob"] == -0.12
    assert "asr_confidence" not in record["provenance"]
    assert "transcript" not in record


def test_merge_batches_to_jsonl_maps_legacy_asr_confidence_to_avg_logprob(
    support_schema: dict,
) -> None:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    project = Job(
        id=project_id,
        user_id=uuid.uuid4(),
        correlation_id="corr-export-audio-legacy",
        name="Audio calls",
        schema_template="support_call_audio",
        schema_json=support_schema,
        domain="audio",
        status=JobStatus.RUNNING.value,
    )
    asset = Asset(
        id=asset_id,
        job_id=project_id,
        filename="call_001.wav",
        mime_type="audio/wav",
        storage_uri="uploads/project/call_001.wav",
        fetch_status=AssetFetchStatus.OK.value,
    )
    segments = [
        Segment(
            id=segment_id,
            job_id=project_id,
            asset_id=asset_id,
            segment_index=0,
            content="Legacy metadata row.",
            start_offset=0,
            end_offset=16_000,
            metadata_json={
                "kind": "audio_utterance",
                "asr_model": "faster-whisper/small",
                "asr_confidence": -0.2191,
            },
        ),
    ]
    batches = [
        AnnotationBatch(
            job_id=project_id,
            task_id=uuid.uuid4(),
            task_index=0,
            labels_json={str(segment_id): {"topic": "billing"}},
            segment_count=1,
            confidence=Decimal("0.8700"),
        ),
    ]

    result = merge_batches_to_jsonl(project, batches, segments, {asset_id: asset})

    record = json.loads(result.jsonl.splitlines()[0])
    assert record["provenance"]["asr_avg_logprob"] == -0.2191
    assert "asr_confidence" not in record["provenance"]


def test_build_qc_report_flags_low_confidence_and_incomplete_coverage(
    support_schema: dict,
) -> None:
    project = Job(
        user_id=uuid.uuid4(),
        correlation_id="corr-qc",
        name="QC run",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=support_schema,
        status=JobStatus.RUNNING.value,
    )
    segment_id = uuid.uuid4()
    records = merge_batches_to_jsonl(
        project,
        [
            AnnotationBatch(
                job_id=project.id,
                task_id=uuid.uuid4(),
                task_index=0,
                labels_json={
                    "segments": [
                        {
                            "segment_id": str(segment_id),
                            "labels": {
                                "emotion": "frustrated",
                                "intent": "complaint",
                                "topic": "billing",
                                "resolution_status": "unresolved",
                            },
                            "confidence": 0.2,
                        }
                    ]
                },
                segment_count=1,
                confidence=Decimal("0.2000"),
            )
        ],
        [
            Segment(
                id=segment_id,
                job_id=project.id,
                asset_id=uuid.uuid4(),
                segment_index=0,
                content="Only one labeled segment",
            ),
            Segment(
                id=uuid.uuid4(),
                job_id=project.id,
                asset_id=uuid.uuid4(),
                segment_index=1,
                content="Unlabeled segment",
            ),
        ],
        {},
    ).records

    report = build_qc_report(
        project=project,
        records=records,
        total_segments=2,
        batch_count=1,
        total_cost_usd=Decimal("0.001234"),
    )

    assert report.coverage_pct == 50.0
    assert report.schema_compliance_pct == 100.0
    assert report.low_confidence_segment_ids == [str(segment_id)]
    assert report.total_cost_usd == pytest.approx(0.001234)
    assert "incomplete_coverage" in report.flags
    assert "low_confidence_segments" in report.flags


def test_build_qc_report_flags_empty_transcripts_for_audio_project(
    support_schema: dict,
) -> None:
    project = Job(
        user_id=uuid.uuid4(),
        correlation_id="corr-qc-audio",
        name="Audio QC",
        schema_template="support_call_audio",
        schema_json=support_schema,
        domain="audio",
        status=JobStatus.RUNNING.value,
    )
    segment_id = uuid.uuid4()
    segments = [
        Segment(
            id=segment_id,
            job_id=project.id,
            asset_id=uuid.uuid4(),
            segment_index=0,
            content="Valid transcript",
        ),
        Segment(
            id=uuid.uuid4(),
            job_id=project.id,
            asset_id=uuid.uuid4(),
            segment_index=1,
            content="   ",
        ),
    ]
    records = merge_batches_to_jsonl(
        project,
        [
            AnnotationBatch(
                job_id=project.id,
                task_id=uuid.uuid4(),
                task_index=0,
                labels_json={
                    str(segment_id): {
                        "emotion": "neutral",
                        "intent": "question",
                        "topic": "billing",
                        "resolution_status": "resolved",
                    }
                },
                segment_count=1,
                confidence=Decimal("0.9000"),
            )
        ],
        segments,
        {},
    ).records

    report = build_qc_report(
        project=project,
        records=records,
        total_segments=len(segments),
        batch_count=1,
        total_cost_usd=Decimal("0"),
        segments=segments,
    )

    assert report.empty_transcript_count == 1
    assert "empty_transcripts" in report.flags


def test_build_qc_report_empty_transcript_count_zero_for_documents(
    support_schema: dict,
) -> None:
    project = Job(
        user_id=uuid.uuid4(),
        correlation_id="corr-qc-docs",
        name="Docs",
        schema_template=SUPPORT_CALL_TEMPLATE,
        schema_json=support_schema,
        domain="documents",
        status=JobStatus.RUNNING.value,
    )
    report = build_qc_report(
        project=project,
        records=[],
        total_segments=0,
        batch_count=0,
        total_cost_usd=Decimal("0"),
        segments=[],
    )
    assert report.empty_transcript_count == 0
    assert "empty_transcripts" not in report.flags
