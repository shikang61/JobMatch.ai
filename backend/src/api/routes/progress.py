"""
Progress: GET /api/progress/stats and GET /api/progress/preparations.
"""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.database.connection import get_db
from src.models.profile import UserProfile
from src.models.interview import InterviewPrepKit, InterviewSession
from src.models.job import Job, JobMatch

router = APIRouter()


class ProgressStatsResponse(BaseModel):
    sessions_completed: int
    average_score: float | None
    total_questions_practiced: int
    readiness_percentage: float


class JobPreparationItem(BaseModel):
    """One job match with its interview prep progress."""
    match_id: str
    job_id: str
    job_title: str
    company_name: str
    compatibility_score: float
    has_prep_kit: bool
    prep_kit_id: str | None
    sessions_completed: int
    total_sessions: int
    last_practice_at: datetime | None
    best_score: int | None
    readiness_score: float  # 0-100 for this job only


class ProgressPreparationsResponse(BaseModel):
    preparations: list[JobPreparationItem]


@router.get("/stats", response_model=ProgressStatsResponse)
async def get_progress_stats(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate progress: sessions completed, average score, readiness."""
    check_api_rate_limit(request, user_id)
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == UUID(user_id))
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return ProgressStatsResponse(
            sessions_completed=0,
            average_score=None,
            total_questions_practiced=0,
            readiness_percentage=0.0,
        )
    count_result = await db.execute(
        select(func.count(InterviewSession.id))
        .join(InterviewPrepKit, InterviewPrepKit.id == InterviewSession.prep_kit_id)
        .join(JobMatch, JobMatch.id == InterviewPrepKit.job_match_id)
        .where(
            JobMatch.user_profile_id == profile.id,
            InterviewSession.status == "completed",
        )
    )
    sessions_completed = count_result.scalar() or 0
    avg_result = await db.execute(
        select(func.avg(InterviewSession.performance_score))
        .join(InterviewPrepKit, InterviewPrepKit.id == InterviewSession.prep_kit_id)
        .join(JobMatch, JobMatch.id == InterviewPrepKit.job_match_id)
        .where(
            JobMatch.user_profile_id == profile.id,
            InterviewSession.status == "completed",
            InterviewSession.performance_score.isnot(None),
        )
    )
    avg_score = avg_result.scalar()
    total_q = 0
    if sessions_completed > 0:
        trans_result = await db.execute(
            select(InterviewSession.transcript)
            .join(InterviewPrepKit, InterviewPrepKit.id == InterviewSession.prep_kit_id)
            .join(JobMatch, JobMatch.id == InterviewPrepKit.job_match_id)
            .where(
                JobMatch.user_profile_id == profile.id,
                InterviewSession.status == "completed",
            )
        )
        for (transcript,) in trans_result:
            if isinstance(transcript, list):
                total_q += len(transcript)
    readiness = min(100.0, sessions_completed * 10.0 + (float(avg_score or 0) * 0.3))
    return ProgressStatsResponse(
        sessions_completed=sessions_completed,
        average_score=float(avg_score) if avg_score is not None else None,
        total_questions_practiced=total_q,
        readiness_percentage=round(readiness, 1),
    )


@router.get("/preparations", response_model=ProgressPreparationsResponse)
async def get_progress_preparations(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List job preparations where the user has started at least one interview practice session."""
    check_api_rate_limit(request, user_id)
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == UUID(user_id))
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return ProgressPreparationsResponse(preparations=[])

    matches_result = await db.execute(
        select(JobMatch, Job)
        .join(Job, Job.id == JobMatch.job_id)
        .where(JobMatch.user_profile_id == profile.id)
        .order_by(JobMatch.compatibility_score.desc())
    )
    rows = matches_result.all()
    preparations: list[JobPreparationItem] = []
    for match, job in rows:
        prep_result = await db.execute(
            select(InterviewPrepKit).where(InterviewPrepKit.job_match_id == match.id)
        )
        prep_kit = prep_result.scalar_one_or_none()
        prep_kit_id = str(prep_kit.id) if prep_kit else None
        sessions_completed = 0
        total_sessions = 0
        last_practice_at: datetime | None = None
        best_score: int | None = None
        if prep_kit:
            sess_result = await db.execute(
                select(
                    func.count(InterviewSession.id).label("total"),
                    func.sum(
                        case((InterviewSession.status == "completed", 1), else_=0)
                    ).label("completed"),
                    func.max(InterviewSession.completed_at).label("last_at"),
                    func.max(InterviewSession.performance_score).label("best"),
                ).where(InterviewSession.prep_kit_id == prep_kit.id)
            )
            row = sess_result.one()
            total_sessions = row.total or 0
            sessions_completed = int(row.completed or 0)
            last_practice_at = row.last_at
            best_score = row.best
        # Only include jobs where the user has started interview practice (≥1 session)
        if total_sessions > 0:
            # Readiness for this job: mix of practice volume and performance (0-100)
            best = best_score or 0
            readiness_score = min(
                100.0,
                (sessions_completed * 15.0) + (best * 0.5),
            )
            preparations.append(
                JobPreparationItem(
                    match_id=str(match.id),
                    job_id=str(job.id),
                    job_title=job.job_title,
                    company_name=job.company_name,
                    compatibility_score=float(match.compatibility_score),
                    has_prep_kit=prep_kit is not None,
                    prep_kit_id=prep_kit_id,
                    sessions_completed=sessions_completed,
                    total_sessions=total_sessions,
                    last_practice_at=last_practice_at,
                    best_score=best_score,
                    readiness_score=round(readiness_score, 1),
                )
            )
    return ProgressPreparationsResponse(preparations=preparations)
