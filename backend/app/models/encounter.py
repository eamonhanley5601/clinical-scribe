import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EncounterStatus(str, enum.Enum):
    draft = "draft"          # transcript/note in progress, not yet finalized
    saved = "saved"          # at least one note_version has been committed
    abandoned = "abandoned"  # e.g. provider deactivated mid-draft; see non-happy-path handling


class Encounter(Base):
    """
    Represents both the in-progress draft AND the saved encounter shell. Session persistence
    works by reading/writing this row directly: there is no separate ephemeral draft store,
    so a refresh, browser change, or new device all resolve to the same DB-backed state.
    """

    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("note_templates.id"), nullable=True
    )
    status: Mapped[EncounterStatus] = mapped_column(
        Enum(EncounterStatus, name="encounter_status"), nullable=False, default=EncounterStatus.draft
    )
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Autosaved draft note fields (pre-save working copy). Overwritten in place on every
    # autosave tick; the immutable history lives in note_versions, written only on explicit Save.
    draft_subjective: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"code": "M54.5", "description": "Low back pain"}, ...] -- structured, lookup-table-
    # verified attachment state (see app.services.icd10_lookup), independent of whatever the
    # Assessment prose happens to say. This is what survives a reload/resume.
    draft_icd10_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
