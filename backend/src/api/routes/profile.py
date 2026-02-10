"""
Profile: CV upload, get/update profile, serve CV file. Requires authentication.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.database.connection import get_db
from src.models.profile import UserProfile
from src.services.cv_parser import extract_text, FileValidationError
from src.services.llm.profile_analyzer import ProfileAnalyzer
from src.services.llm.base import LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
profile_analyzer = ProfileAnalyzer()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SkillCompetency(BaseModel):
    skill: str
    level: int  # 1-5


class ProfileResponse(BaseModel):
    id: str
    user_id: str
    full_name: str | None
    preferred_location: str | None
    has_cv_file: bool
    cv_file_name: str | None
    parsed_skills: list[str]
    skill_competencies: list[SkillCompetency]
    parsed_experience: list[dict]
    parsed_education: list[str]
    experience_years: int | None
    suggested_job_titles: list[str]

    class Config:
        from_attributes = True


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    preferred_location: str | None = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile_response(profile: UserProfile) -> ProfileResponse:
    """Build ProfileResponse from ORM model (single source of truth)."""
    return ProfileResponse(
        id=str(profile.id),
        user_id=str(profile.user_id),
        full_name=profile.full_name,
        preferred_location=profile.preferred_location,
        has_cv_file=profile.cv_file_data is not None and len(profile.cv_file_data) > 0,
        cv_file_name=profile.cv_file_name,
        parsed_skills=profile.parsed_skills or [],
        skill_competencies=[
            SkillCompetency(skill=c.get("skill", ""), level=c.get("level", 3))
            for c in (profile.skill_competencies or [])
            if isinstance(c, dict)
        ],
        parsed_experience=profile.parsed_experience or [],
        parsed_education=profile.parsed_education or [],
        experience_years=profile.experience_years,
        suggested_job_titles=profile.suggested_job_titles or [],
    )


async def get_or_create_profile(db: AsyncSession, user_id: str) -> UserProfile:
    uid = UUID(user_id)
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == uid))
    profile = result.scalar_one_or_none()
    if profile:
        return profile
    profile = UserProfile(user_id=uid)
    db.add(profile)
    await db.flush()
    return profile


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile. Returns empty profile if none yet."""
    check_api_rate_limit(request, user_id)
    profile = await get_or_create_profile(db, user_id)
    return _profile_response(profile)


@router.put("/me", response_model=ProfileResponse)
async def update_my_profile(
    user_id: CurrentUserId,
    request: Request,
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update profile fields (full_name, preferred_location)."""
    check_api_rate_limit(request, user_id)
    profile = await get_or_create_profile(db, user_id)
    if body.full_name is not None:
        profile.full_name = body.full_name[:255] if body.full_name else None
    if body.preferred_location is not None:
        profile.preferred_location = body.preferred_location[:255] if body.preferred_location else None
    await db.commit()
    await db.refresh(profile)
    return _profile_response(profile)


@router.post("/cv-upload", response_model=ProfileResponse)
async def upload_cv(
    user_id: CurrentUserId,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload CV (PDF or DOCX). Extracts text, runs LLM analysis (skills,
    competency levels, suggested job titles), saves everything to profile.
    Max size 5MB. Validates file type by magic bytes.
    """
    check_api_rate_limit(request, user_id)
    content = await file.read()
    content_type = file.content_type
    filename = file.filename or ""

    try:
        raw_text = extract_text(content, content_type, filename)
    except FileValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if len(raw_text.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract enough text from the file.",
        )

    try:
        structured = await profile_analyzer.analyze_cv_text(raw_text)
    except LLMServiceError as e:
        logger.warning("LLM profile analysis failed", extra={"error": str(e)[:200]})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is temporarily unavailable. Please try again.",
        ) from e

    profile = await get_or_create_profile(db, user_id)

    # Store raw file for later viewing
    profile.cv_file_data = content
    profile.cv_file_name = filename[:255] if filename else None
    profile.cv_content_type = content_type[:100] if content_type else "application/octet-stream"
    profile.cv_text = raw_text[:100_000]

    # Parsed data
    profile.full_name = structured.get("full_name") or profile.full_name
    profile.parsed_skills = structured.get("skills") or []
    profile.skill_competencies = structured.get("skill_competencies") or []
    profile.parsed_experience = structured.get("experience") or []
    profile.parsed_education = structured.get("education") or []
    profile.experience_years = structured.get("total_years_experience") or None
    profile.suggested_job_titles = structured.get("suggested_job_titles") or []

    await db.commit()
    await db.refresh(profile)

    logger.info("CV uploaded and parsed", extra={"user_id": user_id[:8]})
    return _profile_response(profile)


@router.get("/cv-file")
async def get_cv_file(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Serve the uploaded CV file (PDF/DOCX) for in-browser viewing.
    Returns the raw file with appropriate Content-Type and Content-Disposition.
    """
    check_api_rate_limit(request, user_id)
    profile = await get_or_create_profile(db, user_id)

    if not profile.cv_file_data:
        raise HTTPException(status_code=404, detail="No CV file uploaded yet.")

    media_type = profile.cv_content_type or "application/octet-stream"
    filename = profile.cv_file_name or "cv"

    # For PDFs, use inline disposition so browser shows it directly
    disposition = "inline" if "pdf" in media_type.lower() else "attachment"

    return Response(
        content=profile.cv_file_data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )
