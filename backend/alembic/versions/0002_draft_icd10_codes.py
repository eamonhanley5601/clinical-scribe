"""add draft_icd10_codes to encounters

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "encounters",
        sa.Column("draft_icd10_codes", postgresql.JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("encounters", "draft_icd10_codes")
