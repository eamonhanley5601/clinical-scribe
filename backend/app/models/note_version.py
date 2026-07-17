import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NoteVersion(Base):
    """
    Append-only. A row is written on every explicit Save; existing rows are never
    updated or deleted, which is what makes this the audit trail (who saved what, when).
    """

    __tablename__ = "note_versions"
    __table_args__ = (
        UniqueConstraint("encounter_id", "version_number", name="uq_note_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    subjective: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    assessment: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"code": "M54.5", "description": "Low back pain"}, ...]
    icd10_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    saved_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
