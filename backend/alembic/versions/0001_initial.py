"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    user_role = postgresql.ENUM("provider", "admin", name="user_role")
    encounter_status = postgresql.ENUM("draft", "saved", "abandoned", name="encounter_status")
    user_role.create(op.get_bind())
    encounter_status.create(op.get_bind())
    # Already created explicitly above; without create_type=False, create_table() would
    # try (and fail) to create each enum type a second time.
    user_role = postgresql.ENUM("provider", "admin", name="user_role", create_type=False)
    encounter_status = postgresql.ENUM("draft", "saved", "abandoned", name="encounter_status", create_type=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("style_profile", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("first_name", sa.String, nullable=False),
        sa.Column("last_name", sa.String, nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("first_name", "last_name", "date_of_birth", name="uq_patient_identity"),
    )
    op.create_index("ix_patients_first_name", "patients", ["first_name"])
    op.create_index("ix_patients_last_name", "patients", ["last_name"])

    op.create_table(
        "note_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("encounter_type", sa.String, nullable=False),
        sa.Column("prompt_instructions", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("note_templates.id"), nullable=True),
        sa.Column("status", encounter_status, nullable=False, server_default="draft"),
        sa.Column("transcript_text", sa.Text, nullable=True),
        sa.Column("draft_subjective", sa.Text, nullable=True),
        sa.Column("draft_objective", sa.Text, nullable=True),
        sa.Column("draft_assessment", sa.Text, nullable=True),
        sa.Column("draft_plan", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"])
    op.create_index("ix_encounters_provider_id", "encounters", ["provider_id"])

    op.create_table(
        "note_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("subjective", sa.Text, nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("assessment", sa.Text, nullable=False),
        sa.Column("plan", sa.Text, nullable=False),
        sa.Column("icd10_codes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("saved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("encounter_id", "version_number", name="uq_note_version_number"),
    )
    op.create_index("ix_note_versions_encounter_id", "note_versions", ["encounter_id"])

    op.create_table(
        "icd10_codes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String, nullable=False, unique=True),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
    )
    op.create_index("ix_icd10_codes_code", "icd10_codes", ["code"])
    # IVFFlat index for approximate nearest-neighbor cosine search at this table size;
    # exact scan would be fine at 231 rows too, but this is the defensible choice at scale.
    op.execute(
        "CREATE INDEX ix_icd10_embedding_cosine ON icd10_codes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("icd10_codes")
    op.drop_table("note_versions")
    op.drop_table("encounters")
    op.drop_table("note_templates")
    op.drop_table("patients")
    op.drop_table("users")
    op.execute("DROP TYPE encounter_status")
    op.execute("DROP TYPE user_role")
