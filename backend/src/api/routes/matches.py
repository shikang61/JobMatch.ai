"""
Job matches: get top matches for current user profile. Trigger (re)compute.
"""
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.config import get_settings
from src.database.connection import get_db
from src.models.profile import UserProfile
from src.models.job import Job, JobMatch
from src.services.matching.job_matcher import compute_match_score
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class MatchResponse(BaseModel):
    id: str
    job_id: str
    compatibility_score: float
    match_details: dict
    job_title: str
    company_name: str
    location: str | None
    job_url: str | None
    posted_date: str | None
    industry: str | None = None


class MatchListResponse(BaseModel):
    matches: list[MatchResponse]
    total: int


async def _get_profile(db: AsyncSession, user_id: str) -> UserProfile | None:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == UUID(user_id))
    )
    return result.scalar_one_or_none()


async def _compute_and_save_matches(db: AsyncSession, profile: UserProfile) -> list[JobMatch]:
    """Load active jobs, compute scores, persist matches, return top N."""
    settings = get_settings()
    result = await db.execute(select(Job).where(Job.is_active.is_(True)))
    jobs = result.scalars().all()
    new_matches: list[JobMatch] = []
    for job in jobs:
        score, details = compute_match_score(
            profile_skills=profile.parsed_skills,
            profile_experience_years=profile.experience_years,
            profile_location=profile.preferred_location,
            job_required_skills=job.required_skills,
            job_preferred_skills=job.preferred_skills,
            job_experience_level=job.experience_level,
            job_experience_years_range=job.experience_years_range,
            job_location=job.location,
            job_posted_date=job.posted_date,
        )
        if score < settings.match_min_compatibility:
            continue
        existing = await db.execute(
            select(JobMatch).where(
                JobMatch.user_profile_id == profile.id,
                JobMatch.job_id == job.id,
            )
        )
        match_row = existing.scalar_one_or_none()
        if match_row:
            match_row.compatibility_score = Decimal(str(score))
            match_row.match_details = details
            new_matches.append(match_row)
        else:
            match_row = JobMatch(
                user_profile_id=profile.id,
                job_id=job.id,
                compatibility_score=Decimal(str(score)),
                match_details=details,
            )
            db.add(match_row)
            await db.flush()
            new_matches.append(match_row)
    await db.commit()
    # Sort and return top N
    new_matches.sort(key=lambda m: m.compatibility_score, reverse=True)
    return new_matches[: settings.match_top_n]


@router.get("/matches", response_model=MatchListResponse)
async def get_my_matches(
    user_id: CurrentUserId,
    request: Request,
    recompute: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Get job matches for current user. If profile has no matches yet, computes them.
    Pass ?recompute=true to force recompute (e.g. after scraping new jobs).
    Returns top matches above minimum compatibility (default 60%).
    """
    check_api_rate_limit(request, user_id)
    profile = await _get_profile(db, user_id)
    if not profile:
        return MatchListResponse(matches=[], total=0)

    if recompute:
        await _compute_and_save_matches(db, profile)

    # Load existing matches with job
    result = await db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .where(JobMatch.user_profile_id == profile.id)
        .order_by(JobMatch.compatibility_score.desc())
    )
    rows = result.all()
    if not rows:
        await _compute_and_save_matches(db, profile)
        result2 = await db.execute(
            select(JobMatch, Job)
            .join(Job, JobMatch.job_id == Job.id)
            .where(JobMatch.user_profile_id == profile.id)
            .order_by(JobMatch.compatibility_score.desc())
        )
        rows = result2.all()
    out = []
    for match, job in rows:
        summary = job.job_summary or {}
        industry = (summary.get("industry") or "").strip() or None
        out.append(
            MatchResponse(
                id=str(match.id),
                job_id=str(job.id),
                compatibility_score=float(match.compatibility_score),
                match_details=match.match_details or {},
                job_title=job.job_title,
                company_name=job.company_name,
                location=job.location,
                job_url=job.job_url,
                posted_date=job.posted_date.isoformat() if job.posted_date else None,
                industry=industry,
            )
        )
    return MatchListResponse(matches=out, total=len(out))
