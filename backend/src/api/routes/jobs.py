"""
Jobs: list matches for current user, get job by id. Requires auth.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.database.connection import get_db
from src.models.job import Job
from src.services.llm.job_analyzer import JobAnalyzer
from src.services.llm.base import LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
job_analyzer = JobAnalyzer()


class JobSummaryResponse(BaseModel):
    key_skills: list[str]
    qualifications: list[str]
    cultural_fit: str
    advantageous_skills: list[str]
    expected_salary: str = ""
    industry: str = ""


class JobResponse(BaseModel):
    id: str
    company_name: str
    job_title: str
    job_description: str
    required_skills: list
    preferred_skills: list
    experience_level: str | None
    location: str | None
    job_url: str | None
    source: str | None
    posted_date: str | None
    job_summary: JobSummaryResponse | None = None

    class Config:
        from_attributes = True


def _to_summary_response(raw: dict | None) -> JobSummaryResponse | None:
    if not raw or not isinstance(raw, dict):
        return None
    return JobSummaryResponse(
        key_skills=raw.get("key_skills") or [],
        qualifications=raw.get("qualifications") or [],
        cultural_fit=raw.get("cultural_fit") or "",
        advantageous_skills=raw.get("advantageous_skills") or [],
        expected_salary=raw.get("expected_salary") or "",
        industry=raw.get("industry") or "",
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get a single job by id. Generates job summary (key skills, cultural fit, etc.) if missing."""
    check_api_rate_limit(request, user_id)
    result = await db.execute(select(Job).where(Job.id == job_id, Job.is_active.is_(True)))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    summary = _to_summary_response(job.job_summary)
    if summary is None and job.job_description:
        try:
            raw_summary = await job_analyzer.summarize_for_candidate(
                job_title=job.job_title,
                company_name=job.company_name,
                description=job.job_description,
            )
            job.job_summary = raw_summary
            await db.commit()
            await db.refresh(job)
            summary = _to_summary_response(raw_summary)
        except LLMServiceError as e:
            logger.warning("Job summary generation failed: %s", e)
    return JobResponse(
        id=str(job.id),
        company_name=job.company_name,
        job_title=job.job_title,
        job_description=job.job_description,
        required_skills=job.required_skills or [],
        preferred_skills=job.preferred_skills or [],
        experience_level=job.experience_level,
        location=job.location,
        job_url=job.job_url,
        source=job.source,
        posted_date=job.posted_date.isoformat() if job.posted_date else None,
        job_summary=summary,
    )
