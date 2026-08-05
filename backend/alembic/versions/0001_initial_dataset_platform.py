"""initial dataset platform schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-05 01:00:00.000000

Fresh baseline after pivot — no pgvector, no legacy research tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("worker_name", sa.String(length=64), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", "worker_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("auth_subject_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_subject_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("schema_template", sa.String(length=64), nullable=True),
        sa.Column("domain", sa.String(length=32), server_default="documents", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id"),
    )
    op.create_index(op.f("ix_jobs_correlation_id"), "jobs", ["correlation_id"], unique=True)
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)

    op.create_table(
        "job_stages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "stage", name="uq_job_stages_job_id_stage"),
    )
    op.create_index(op.f("ix_job_stages_job_id"), "job_stages", ["job_id"], unique=False)

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_job_id"), "llm_usage", ["job_id"], unique=False)

    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=2048), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.Text(), nullable=True),
        sa.Column("fetch_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_job_id"), "assets", ["job_id"], unique=False)

    op.create_table(
        "segments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "segment_index", name="uq_segments_asset_id_segment_index"
        ),
    )
    op.create_index(op.f("ix_segments_job_id"), "segments", ["job_id"], unique=False)
    op.create_index(op.f("ix_segments_asset_id"), "segments", ["asset_id"], unique=False)

    op.create_table(
        "annotation_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("task_index", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("segment_ids_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "task_index", name="uq_annotation_tasks_job_id_task_index"
        ),
    )
    op.create_index(
        op.f("ix_annotation_tasks_job_id"), "annotation_tasks", ["job_id"], unique=False
    )

    op.create_table(
        "annotation_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("task_index", sa.Integer(), nullable=False),
        sa.Column("labels_json", sa.Text(), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "task_index", name="uq_annotation_batches_job_id_task_index"
        ),
        sa.UniqueConstraint("task_id", name="uq_annotation_batches_task_id"),
    )
    op.create_index(
        op.f("ix_annotation_batches_job_id"), "annotation_batches", ["job_id"], unique=False
    )

    op.create_table(
        "dataset_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("export_content", sa.Text(), nullable=False),
        sa.Column("qc_report_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        op.f("ix_dataset_exports_job_id"), "dataset_exports", ["job_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dataset_exports_job_id"), table_name="dataset_exports")
    op.drop_table("dataset_exports")
    op.drop_index(op.f("ix_annotation_batches_job_id"), table_name="annotation_batches")
    op.drop_table("annotation_batches")
    op.drop_index(op.f("ix_annotation_tasks_job_id"), table_name="annotation_tasks")
    op.drop_table("annotation_tasks")
    op.drop_index(op.f("ix_segments_asset_id"), table_name="segments")
    op.drop_index(op.f("ix_segments_job_id"), table_name="segments")
    op.drop_table("segments")
    op.drop_index(op.f("ix_assets_job_id"), table_name="assets")
    op.drop_table("assets")
    op.drop_index(op.f("ix_llm_usage_job_id"), table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_index(op.f("ix_job_stages_job_id"), table_name="job_stages")
    op.drop_table("job_stages")
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_correlation_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("users")
    op.drop_table("processed_events")
