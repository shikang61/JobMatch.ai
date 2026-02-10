"""
Interview prep kit and session models.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import Base


class InterviewPrepKit(Base):
    __tablename__ = "interview_prep_kits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    company_insights: Mapped[str | None] = mapped_column(Text, nullable=True)
    tips: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job_match = relationship("JobMatch", back_populates="prep_kits")
    sessions = relationship(
        "InterviewSession",
        back_populates="prep_kit",
        cascade="all, delete-orphan",
    )


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prep_kit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_prep_kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transcript: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    performance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="in_progress", nullable=False, index=True
    )
    answers_json: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    questions_used: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    prep_kit = relationship("InterviewPrepKit", back_populates="sessions")
