"""schema integrity and jsonb columns

Revision ID: 0002_schema_integrity
Revises: 0001_initial
Create Date: 2026-08-05 21:00:00.000000

- annotation_task_segments junction table (replaces segment_ids_json)
- FK annotation_batches.task_id -> annotation_tasks.id
- Text JSON columns -> JSONB
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_schema_integrity"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _segment_ids_from_payload(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        segment_ids = parsed.get("segment_ids", [])
        if isinstance(segment_ids, list):
            return [str(segment_id) for segment_id in segment_ids]
        return []
    if isinstance(parsed, list):
        return [str(segment_id) for segment_id in parsed]
    return []


def upgrade() -> None:
    op.create_table(
        "annotation_task_segments",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("segment_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["annotation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "segment_id"),
        sa.UniqueConstraint(
            "task_id",
            "position",
            name="uq_annotation_task_segments_task_position",
        ),
    )
    op.create_index(
        op.f("ix_annotation_task_segments_segment_id"),
        "annotation_task_segments",
        ["segment_id"],
        unique=False,
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, segment_ids_json FROM annotation_tasks")
    ).fetchall()
    for row in rows:
        segment_ids = _segment_ids_from_payload(row.segment_ids_json)
        for position, segment_id in enumerate(segment_ids):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO annotation_task_segments (task_id, segment_id, position)
                    VALUES (:task_id, :segment_id, :position)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"task_id": row.id, "segment_id": segment_id, "position": position},
            )

    op.drop_column("annotation_tasks", "segment_ids_json")

    op.create_foreign_key(
        "fk_annotation_batches_task_id_annotation_tasks",
        "annotation_batches",
        "annotation_tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column(
        "jobs",
        "schema_json",
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using="schema_json::jsonb",
        existing_nullable=False,
    )
    op.alter_column(
        "annotation_batches",
        "labels_json",
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using="labels_json::jsonb",
        existing_nullable=False,
    )
    op.alter_column(
        "dataset_exports",
        "qc_report_json",
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using="qc_report_json::jsonb",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "dataset_exports",
        "qc_report_json",
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using="qc_report_json::text",
        existing_nullable=False,
    )
    op.alter_column(
        "annotation_batches",
        "labels_json",
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using="labels_json::text",
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "schema_json",
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using="schema_json::text",
        existing_nullable=False,
    )

    op.drop_constraint(
        "fk_annotation_batches_task_id_annotation_tasks",
        "annotation_batches",
        type_="foreignkey",
    )

    op.add_column(
        "annotation_tasks",
        sa.Column("segment_ids_json", sa.Text(), nullable=False, server_default="{}"),
    )
    connection = op.get_bind()
    tasks = connection.execute(sa.text("SELECT id FROM annotation_tasks")).fetchall()
    for task in tasks:
        links = connection.execute(
            sa.text(
                """
                SELECT segment_id
                FROM annotation_task_segments
                WHERE task_id = :task_id
                ORDER BY position
                """
            ),
            {"task_id": task.id},
        ).fetchall()
        payload = json.dumps({"segment_ids": [str(link.segment_id) for link in links]})
        connection.execute(
            sa.text(
                "UPDATE annotation_tasks SET segment_ids_json = :payload WHERE id = :task_id"
            ),
            {"payload": payload, "task_id": task.id},
        )
    op.alter_column("annotation_tasks", "segment_ids_json", server_default=None)

    op.drop_index(
        op.f("ix_annotation_task_segments_segment_id"),
        table_name="annotation_task_segments",
    )
    op.drop_table("annotation_task_segments")
