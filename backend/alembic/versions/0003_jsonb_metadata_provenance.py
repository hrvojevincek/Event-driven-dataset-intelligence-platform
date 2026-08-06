"""jsonb metadata_json and provenance

Revision ID: 0003_jsonb_metadata_provenance
Revises: 0002_schema_integrity
Create Date: 2026-08-06 08:00:00.000000

- segments.metadata_json Text -> JSONB (nullable)
- assets.provenance Text -> JSONB (nullable)
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_jsonb_metadata_provenance"
down_revision: str | Sequence[str] | None = "0002_schema_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _repair_text_json_column(
    connection: sa.Connection,
    *,
    table: str,
    column: str,
) -> None:
    """Normalize Text values so a subsequent ``::jsonb`` cast cannot fail."""
    connection.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET {column} = NULL
            WHERE {column} IS NOT NULL AND btrim({column}) = ''
            """
        )
    )
    rows = connection.execute(
        sa.text(f"SELECT id, {column} AS raw_value FROM {table} WHERE {column} IS NOT NULL")
    ).fetchall()
    for row in rows:
        raw_value = row.raw_value
        if not isinstance(raw_value, str):
            continue
        try:
            json.loads(raw_value)
        except json.JSONDecodeError:
            connection.execute(
                sa.text(f"UPDATE {table} SET {column} = :payload WHERE id = :id"),
                {"payload": json.dumps({"_legacy_text": raw_value}), "id": row.id},
            )


def upgrade() -> None:
    connection = op.get_bind()
    _repair_text_json_column(connection, table="segments", column="metadata_json")
    _repair_text_json_column(connection, table="assets", column="provenance")

    op.alter_column(
        "segments",
        "metadata_json",
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using="metadata_json::jsonb",
        existing_nullable=True,
    )
    op.alter_column(
        "assets",
        "provenance",
        existing_type=sa.Text(),
        type_=JSONB(),
        postgresql_using="provenance::jsonb",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "provenance",
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using="provenance::text",
        existing_nullable=True,
    )
    op.alter_column(
        "segments",
        "metadata_json",
        existing_type=JSONB(),
        type_=sa.Text(),
        postgresql_using="metadata_json::text",
        existing_nullable=True,
    )
