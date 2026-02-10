"""
Job and job match SQLAlchemy models.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferred_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_years_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    key_responsibilities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(500), unique=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    raw_html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    job_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    matches = relationship(
        "JobMatch", back_populates="job", cascade="all, delete-orphan"
    )


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    compatibility_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, index=True
    )
    match_details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user_profile = relationship("UserProfile", back_populates="job_matches")
    job = relationship("Job", back_populates="matches")
    prep_kits = relationship(
        "InterviewPrepKit",
        back_populates="job_match",
        cascade="all, delete-orphan",
    )
