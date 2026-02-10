"""
User profile and CV data model.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.connection import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # CV storage
    cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cv_file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    cv_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cv_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Parsed from CV via LLM
    parsed_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    parsed_experience: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    parsed_education: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Skill competencies: [{skill: str, level: int (1-5)}]
    skill_competencies: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # LLM-suggested job titles for scraping
    suggested_job_titles: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="profile")
    job_matches = relationship(
        "JobMatch", back_populates="user_profile", cascade="all, delete-orphan"
    )
