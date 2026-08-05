"""Quality-control metrics for dataset exports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eventforge.db.models import Project
from eventforge.services.export.merge import ExportRecord
from eventforge.services.planning.schema_templates import load_label_schema

LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class QCReport:
    """QC summary persisted alongside the JSONL export."""

    coverage_pct: float
    schema_compliance_pct: float
    low_confidence_segment_ids: list[str]
    total_cost_usd: float
    segment_count: int
    labeled_count: int
    batch_count: int
    flags: list[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "coverage_pct": self.coverage_pct,
                "schema_compliance_pct": self.schema_compliance_pct,
                "low_confidence_segment_ids": self.low_confidence_segment_ids,
                "total_cost_usd": self.total_cost_usd,
                "segment_count": self.segment_count,
                "labeled_count": self.labeled_count,
                "batch_count": self.batch_count,
                "flags": self.flags,
            },
            ensure_ascii=False,
        )


def _required_fields(label_schema: dict[str, Any]) -> list[str]:
    required = label_schema.get("required")
    if isinstance(required, list) and required:
        return [str(field) for field in required]
    properties = label_schema.get("properties", {})
    if isinstance(properties, dict):
        return [str(field) for field in properties]
    return []


def _labels_complete(labels: dict[str, str], required: list[str]) -> bool:
    return all(field in labels and bool(labels[field].strip()) for field in required)


def build_qc_report(
    *,
    project: Project,
    records: list[ExportRecord],
    total_segments: int,
    batch_count: int,
    total_cost_usd: Decimal,
) -> QCReport:
    """Compute coverage, schema compliance, and confidence flags for an export."""
    label_schema = load_label_schema(project.schema_json, project.schema_template)
    required = _required_fields(label_schema)

    labeled_count = len(records)
    coverage_pct = (
        100.0
        if total_segments == 0
        else round(
            (labeled_count / total_segments) * 100.0,
            2,
        )
    )

    compliant_count = sum(1 for record in records if _labels_complete(record.labels, required))
    schema_compliance_pct = (
        100.0
        if not records
        else round(
            (compliant_count / len(records)) * 100.0,
            2,
        )
    )

    low_confidence_segment_ids = [
        str(record.segment_id)
        for record in records
        if float(record.provenance.get("confidence", 1.0)) < LOW_CONFIDENCE_THRESHOLD
    ]

    flags: list[str] = []
    if coverage_pct < 100.0:
        flags.append("incomplete_coverage")
    if schema_compliance_pct < 100.0:
        flags.append("schema_noncompliance")
    if low_confidence_segment_ids:
        flags.append("low_confidence_segments")

    return QCReport(
        coverage_pct=coverage_pct,
        schema_compliance_pct=schema_compliance_pct,
        low_confidence_segment_ids=low_confidence_segment_ids,
        total_cost_usd=float(total_cost_usd),
        segment_count=total_segments,
        labeled_count=labeled_count,
        batch_count=batch_count,
        flags=flags,
    )
