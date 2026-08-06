"""jsonb metadata_json and provenance

Revision ID: 0003_jsonb_metadata_provenance
Revises: 0002_schema_integrity
Create Date: 2026-08-06 08:00:00.000000

- segments.metadata_json Text -> JSONB (nullable)
- assets.provenance Text -> JSONB (nullable)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_jsonb_metadata_provenance"
down_revision: str | Sequence[str] | None = "0002_schema_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
