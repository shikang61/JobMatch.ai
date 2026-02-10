"""
Interview prep: generate prep kit, get prep kit, start practice session,
evaluate individual answers, complete session with overall feedback.
Sessions are saved per company (via prep_kit -> job_match -> job).
"""
import random
from uuid import UUID
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.database.connection import get_db
from src.models.profile import UserProfile
from src.models.job import Job, JobMatch
from src.models.interview import InterviewPrepKit, InterviewSession
from src.services.llm.interview_generator import InterviewGenerator
from src.services.llm.base import get_openai_client, chat_completion_json, LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
interview_generator = InterviewGenerator()

VALID_QUESTION_TYPES = frozenset({"behavioral", "technical", "company"})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrepQuestion(BaseModel):
    question: str
    type: str
    category: str
    difficulty: str


class PrepKitResponse(BaseModel):
    id: str
    job_match_id: str
    questions: list[PrepQuestion]
    company_insights: str | None
    tips: list[str]
    job_title: str | None = None
    company_name: str | None = None


class StartSessionRequest(BaseModel):
    prep_kit_id: str
    num_questions: int = Field(default=10, ge=1, le=30, description="Number of questions to practice")
    question_types: list[str] = Field(
        default=["behavioral", "technical", "company"],
        description="Types: behavioral, technical, company",
    )


class StartSessionResponse(BaseModel):
    session_id: str
    prep_kit_id: str
    status: str
    questions: list[PrepQuestion]
    job_title: str
    company_name: str


class EvaluateAnswerRequest(BaseModel):
    session_id: str
    question: str
    question_type: str = "technical"
    answer: str = Field(..., min_length=1, max_length=10000)
    job_title: str = ""
    company_name: str = ""


class EvaluateAnswerResponse(BaseModel):
    score: int  # 1-10
    feedback: str
    strengths: list[str]
    improvements: list[str]


class CompleteSessionRequest(BaseModel):
    session_id: str
    answers: list[dict]  # [{question, answer, score, feedback}]
    job_title: str = ""
    company_name: str = ""


class CompleteSessionResponse(BaseModel):
    overall_score: int  # 0-100
    summary: str
    strengths: list[str]
    areas_to_improve: list[str]
    recommendation: str
    session_id: str


class SessionDetailResponse(BaseModel):
    """Single session with questions and company context (for resuming or viewing saved practice)."""
    session_id: str
    prep_kit_id: str
    status: str
    performance_score: int | None
    completed_at: datetime | None
    questions: list[PrepQuestion]
    job_title: str
    company_name: str
    started_at: datetime


class SessionListItem(BaseModel):
    session_id: str
    status: str
    performance_score: int | None
    completed_at: datetime | None
    started_at: datetime
    job_title: str
    company_name: str
    num_questions: int


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_profile(db: AsyncSession, user_id: str) -> UserProfile | None:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == UUID(user_id))
    )
    return result.scalar_one_or_none()


async def _verify_prep_kit_ownership(
    db: AsyncSession, prep_id: UUID, user_id: str
) -> tuple[InterviewPrepKit, JobMatch]:
    """
    Verify that the prep kit belongs to the authenticated user.
    Joins through: PrepKit -> JobMatch -> UserProfile -> user_id.
    Returns (kit, match) or raises 404.
    """
    result = await db.execute(
        select(InterviewPrepKit, JobMatch)
        .join(JobMatch, InterviewPrepKit.job_match_id == JobMatch.id)
        .join(UserProfile, JobMatch.user_profile_id == UserProfile.id)
        .where(
            InterviewPrepKit.id == prep_id,
            UserProfile.user_id == UUID(user_id),
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prep kit not found")
    return row[0], row[1]


async def _verify_session_ownership(
    db: AsyncSession, session_id: UUID, user_id: str
) -> tuple[InterviewSession, InterviewPrepKit, JobMatch, Job | None]:
    """Verify session belongs to user. Returns (session, kit, match, job) or raises 404."""
    result = await db.execute(
        select(InterviewSession, InterviewPrepKit, JobMatch, Job)
        .join(InterviewPrepKit, InterviewPrepKit.id == InterviewSession.prep_kit_id)
        .join(JobMatch, JobMatch.id == InterviewPrepKit.job_match_id)
        .join(UserProfile, JobMatch.user_profile_id == UserProfile.id)
        .outerjoin(Job, Job.id == JobMatch.job_id)
        .where(
            InterviewSession.id == session_id,
            UserProfile.user_id == UUID(user_id),
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return row[0], row[1], row[2], row[3]


def _to_prep_question(q: dict) -> PrepQuestion:
    return PrepQuestion(
        question=q.get("question") or "",
        type=q.get("type") or "technical",
        category=q.get("category") or "general",
        difficulty=q.get("difficulty") or "medium",
    )


# ---------------------------------------------------------------------------
# Prep kit CRUD
# ---------------------------------------------------------------------------

@router.post("/prep/{match_id}", response_model=PrepKitResponse)
async def create_prep_kit(
    match_id: UUID,
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate interview prep kit for a job match. Idempotent: returns existing if present."""
    check_api_rate_limit(request, user_id)
    profile = await _get_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Upload a CV first to get matches and prep.")

    result = await db.execute(
        select(JobMatch, Job).join(Job, JobMatch.job_id == Job.id).where(
            JobMatch.id == match_id,
            JobMatch.user_profile_id == profile.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    match, job = row

    # Return existing kit if already generated
    kit_result = await db.execute(
        select(InterviewPrepKit).where(InterviewPrepKit.job_match_id == match.id)
    )
    existing = kit_result.scalar_one_or_none()
    if existing:
        return PrepKitResponse(
            id=str(existing.id),
            job_match_id=str(match.id),
            questions=[_to_prep_question(q) for q in (existing.questions or [])],
            company_insights=existing.company_insights,
            tips=existing.tips or [],
            job_title=job.job_title,
            company_name=job.company_name,
        )

    try:
        missing = (match.match_details or {}).get("missing_required_skills") or []
        data = await interview_generator.generate(
            job_title=job.job_title,
            company_name=job.company_name,
            job_description=job.job_description,
            required_skills=job.required_skills or [],
            profile_skills=profile.parsed_skills or [],
            missing_skills=missing,
        )
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail="Interview prep generation unavailable.") from e

    kit = InterviewPrepKit(
        job_match_id=match.id,
        questions=data["questions"],
        company_insights=data.get("company_insights") or "",
        tips=data.get("tips") or [],
    )
    db.add(kit)
    await db.commit()
    await db.refresh(kit)
    return PrepKitResponse(
        id=str(kit.id),
        job_match_id=str(match.id),
        questions=[_to_prep_question(q) for q in kit.questions],
        company_insights=kit.company_insights,
        tips=kit.tips or [],
        job_title=job.job_title,
        company_name=job.company_name,
    )


@router.get("/prep/{prep_id}", response_model=PrepKitResponse)
async def get_prep_kit(
    prep_id: UUID,
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get interview prep kit by id. Verifies ownership through profile."""
    check_api_rate_limit(request, user_id)
    kit, match = await _verify_prep_kit_ownership(db, prep_id, user_id)
    result = await db.execute(select(Job).where(Job.id == match.job_id))
    job = result.scalar_one_or_none()
    return PrepKitResponse(
        id=str(kit.id),
        job_match_id=str(match.id),
        questions=[_to_prep_question(q) for q in (kit.questions or [])],
        company_insights=kit.company_insights,
        tips=kit.tips or [],
        job_title=job.job_title if job else None,
        company_name=job.company_name if job else None,
    )


# ---------------------------------------------------------------------------
# Practice session
# ---------------------------------------------------------------------------

def _filter_questions(
    kit_questions: list[dict],
    question_types: list[str],
    num_questions: int,
) -> list[dict]:
    """Filter kit questions by type and take up to num_questions (shuffled for variety)."""
    types_set = {t.lower() for t in question_types if t.lower() in VALID_QUESTION_TYPES}
    if not types_set:
        types_set = VALID_QUESTION_TYPES
    filtered = [
        q for q in (kit_questions or [])
        if (q.get("type") or "technical").lower() in types_set
    ]
    random.shuffle(filtered)
    return filtered[:num_questions]


@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    user_id: CurrentUserId,
    request: Request,
    body: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a practice session for a prep kit. Optionally limit count and question types."""
    check_api_rate_limit(request, user_id)
    prep_id = UUID(body.prep_kit_id)
    kit, match = await _verify_prep_kit_ownership(db, prep_id, user_id)
    # Resolve job for job_title / company_name
    result = await db.execute(select(Job).where(Job.id == match.job_id))
    job = result.scalar_one_or_none()
    job_title = job.job_title if job else ""
    company_name = job.company_name if job else ""

    raw_questions = kit.questions or []
    selected = _filter_questions(
        raw_questions,
        body.question_types,
        body.num_questions,
    )
    if not selected:
        selected = raw_questions[: body.num_questions]
    selected = [
        {
            "question": (q.get("question") if isinstance(q, dict) else "") or "",
            "type": (q.get("type") if isinstance(q, dict) else "technical") or "technical",
            "category": (q.get("category") if isinstance(q, dict) else "general") or "general",
            "difficulty": (q.get("difficulty") if isinstance(q, dict) else "medium") or "medium",
        }
        for q in selected
    ]

    if not selected:
        raise HTTPException(
            status_code=400,
            detail="No questions available for the selected types or count. Try different question types or add more questions to the prep kit.",
        )

    session = InterviewSession(
        prep_kit_id=kit.id,
        status="in_progress",
        questions_used=selected,
    )
    db.add(session)
    try:
        await db.commit()
        await db.refresh(session)
    except OperationalError as e:
        await db.rollback()
        msg = str(e).lower()
        if "questions_used" in msg or "column" in msg:
            logger.warning("Session create failed, possibly missing migration: %s", e)
            raise HTTPException(
                status_code=503,
                detail="Database schema is outdated. Run migration: database/migrations/003_session_questions_used.sql",
            ) from e
        raise
    return StartSessionResponse(
        session_id=str(session.id),
        prep_kit_id=str(kit.id),
        status=session.status,
        questions=[_to_prep_question(q) for q in selected],
        job_title=job_title,
        company_name=company_name,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: CurrentUserId,
    request: Request,
    prep_kit_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List practice sessions. Optionally filter by prep_kit_id (one company/job)."""
    check_api_rate_limit(request, user_id)
    profile = await _get_profile(db, user_id)
    if not profile:
        return SessionListResponse(sessions=[])

    q = (
        select(InterviewSession, Job)
        .join(InterviewPrepKit, InterviewPrepKit.id == InterviewSession.prep_kit_id)
        .join(JobMatch, JobMatch.id == InterviewPrepKit.job_match_id)
        .join(UserProfile, JobMatch.user_profile_id == UserProfile.id)
        .outerjoin(Job, Job.id == JobMatch.job_id)
        .where(UserProfile.user_id == UUID(user_id))
        .order_by(InterviewSession.started_at.desc())
    )
    if prep_kit_id is not None:
        q = q.where(InterviewPrepKit.id == prep_kit_id)
    result = await db.execute(q.limit(50))
    rows = result.all()
    sessions_list = []
    for session, job in rows:
        qu = session.questions_used or []
        sessions_list.append(
            SessionListItem(
                session_id=str(session.id),
                status=session.status,
                performance_score=session.performance_score,
                completed_at=session.completed_at,
                started_at=session.started_at,
                job_title=job.job_title if job else "",
                company_name=job.company_name if job else "",
                num_questions=len(qu),
            )
        )
    return SessionListResponse(sessions=sessions_list)


@router.get("/session/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get a practice session by id (for resuming or viewing saved practice for this company)."""
    check_api_rate_limit(request, user_id)
    session, kit, match, job = await _verify_session_ownership(db, session_id, user_id)
    questions_raw = session.questions_used or []
    questions = [_to_prep_question(q) for q in questions_raw]
    return SessionDetailResponse(
        session_id=str(session.id),
        prep_kit_id=str(kit.id),
        status=session.status,
        performance_score=session.performance_score,
        completed_at=session.completed_at,
        questions=questions,
        job_title=job.job_title if job else "",
        company_name=job.company_name if job else "",
        started_at=session.started_at,
    )


EVALUATE_SYSTEM = """You are an expert interview coach evaluating a candidate's answer.
Score the answer 1-10 and provide constructive feedback.

Respond with JSON:
{
  "score": <1-10>,
  "feedback": "<2-3 sentences of feedback>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>"]
}

Be encouraging but honest. For behavioral questions, check for STAR method usage.
For technical questions, check accuracy and depth. Score 7+ for good answers."""


@router.post("/evaluate-answer", response_model=EvaluateAnswerResponse)
async def evaluate_answer(
    user_id: CurrentUserId,
    request: Request,
    body: EvaluateAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a single interview answer using LLM. Returns score and feedback."""
    check_api_rate_limit(request, user_id)

    user_content = (
        f"Job: {body.job_title} at {body.company_name}\n"
        f"Question type: {body.question_type}\n"
        f"Question: {body.question}\n\n"
        f"Candidate's answer:\n{body.answer[:5000]}"
    )

    try:
        client = get_openai_client()
        data = await chat_completion_json(
            client,
            system_prompt=EVALUATE_SYSTEM,
            user_content=user_content,
            max_tokens=500,
        )
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail="Evaluation unavailable.") from e

    score = data.get("score", 5)
    if not isinstance(score, int) or score < 1 or score > 10:
        score = 5

    # Save answer to session if session_id provided
    if body.session_id:
        try:
            sid = UUID(body.session_id)
            result = await db.execute(select(InterviewSession).where(InterviewSession.id == sid))
            session = result.scalar_one_or_none()
            if session:
                answers = session.answers_json or []
                answers.append({
                    "question": body.question,
                    "answer": body.answer[:5000],
                    "score": score,
                    "feedback": data.get("feedback", ""),
                })
                session.answers_json = answers
                await db.commit()
        except Exception:
            logger.warning("Failed to save answer to session")

    return EvaluateAnswerResponse(
        score=score,
        feedback=data.get("feedback") or "",
        strengths=data.get("strengths") or [],
        improvements=data.get("improvements") or [],
    )


COMPLETE_SYSTEM = """You are an expert interview coach providing a final performance review.
Analyze the candidate's overall interview performance across all questions.

Respond with JSON:
{
  "overall_score": <0-100>,
  "summary": "<3-4 sentence summary of the interview performance>",
  "strengths": ["<top strength 1>", "<top strength 2>", "<top strength 3>"],
  "areas_to_improve": ["<area 1>", "<area 2>", "<area 3>"],
  "recommendation": "<1-2 sentence recommendation for next steps>"
}

Be balanced, constructive, and specific. Reference actual answers where possible."""


@router.post("/complete-session", response_model=CompleteSessionResponse)
async def complete_session(
    user_id: CurrentUserId,
    request: Request,
    body: CompleteSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Complete the practice session. Provides overall score and detailed feedback."""
    check_api_rate_limit(request, user_id)

    # Build transcript for LLM evaluation
    transcript_lines = [f"Interview for: {body.job_title} at {body.company_name}\n"]
    for i, qa in enumerate(body.answers[:20], 1):
        transcript_lines.append(
            f"Q{i}: {qa.get('question', '')}\n"
            f"A{i}: {qa.get('answer', '')}\n"
            f"Individual score: {qa.get('score', '?')}/10\n"
        )

    try:
        client = get_openai_client()
        data = await chat_completion_json(
            client,
            system_prompt=COMPLETE_SYSTEM,
            user_content="\n".join(transcript_lines)[:10000],
            max_tokens=800,
        )
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail="Session evaluation unavailable.") from e

    overall_score = data.get("overall_score", 50)
    if not isinstance(overall_score, int) or overall_score < 0 or overall_score > 100:
        overall_score = 50

    # Update session in DB
    if body.session_id:
        try:
            sid = UUID(body.session_id)
            result = await db.execute(select(InterviewSession).where(InterviewSession.id == sid))
            session = result.scalar_one_or_none()
            if session:
                session.status = "completed"
                session.completed_at = datetime.now(timezone.utc)
                session.performance_score = overall_score
                session.transcript = body.answers[:20]
                session.answers_json = body.answers[:20]
                await db.commit()
        except Exception:
            logger.warning("Failed to update session completion")

    return CompleteSessionResponse(
        overall_score=overall_score,
        summary=data.get("summary") or "",
        strengths=data.get("strengths") or [],
        areas_to_improve=data.get("areas_to_improve") or [],
        recommendation=data.get("recommendation") or "",
        session_id=body.session_id,
    )
