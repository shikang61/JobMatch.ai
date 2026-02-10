"""
Job matching algorithm: skill overlap, experience level, location, recency.
Weights: skills 60% (required 40%, preferred 20%), experience 20%, location 10%, recency 10%.
"""
from datetime import date
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

LEVEL_ORDER = ("entry", "mid", "senior", "lead", "executive")


def _normalize_skills(skills: list[str] | None) -> set[str]:
    if not skills:
        return set()
    return set(s.strip().lower() for s in skills if s and isinstance(s, str))


def _experience_level_score(
    profile_years: int | None,
    job_level: str | None,
    job_years_range: str | None,
) -> float:
    """
    Score 0-1: exact level match 1.0, one off 0.6, two+ off 0.2.
    Infer level from profile years and job requirements.
    """
    if not job_level:
        return 0.7  # unknown job level: neutral
    job_level = job_level.strip().lower()
    try:
        job_idx = LEVEL_ORDER.index(job_level)
    except ValueError:
        return 0.7
    # Infer profile level from years
    profile_level = "entry"
    if profile_years is not None:
        if profile_years >= 10:
            profile_level = "executive"
        elif profile_years >= 7:
            profile_level = "lead"
        elif profile_years >= 4:
            profile_level = "senior"
        elif profile_years >= 2:
            profile_level = "mid"
    try:
        profile_idx = LEVEL_ORDER.index(profile_level)
    except ValueError:
        profile_idx = 1
    diff = abs(job_idx - profile_idx)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.6
    return 0.2


def _recency_score(posted_date: date | None) -> float:
    """Posted < 7 days: 1.0, 7-30: 0.7, > 30: 0.4."""
    if not posted_date:
        return 0.7
    days_ago = (date.today() - posted_date).days
    if days_ago < 7:
        return 1.0
    if days_ago < 30:
        return 0.7
    return 0.4


def _location_score(profile_location: str | None, job_location: str | None) -> float:
    """MVP: 1.0 if both empty or either contains the other; else 0.5."""
    if not job_location or not job_location.strip():
        return 1.0
    if not profile_location or not profile_location.strip():
        return 0.7  # no preference
    pl = profile_location.lower().strip()
    jl = job_location.lower().strip()
    if pl in jl or jl in pl:
        return 1.0
    return 0.5


def compute_match_score(
    profile_skills: list[str] | None,
    profile_experience_years: int | None,
    profile_location: str | None,
    job_required_skills: list[str] | None,
    job_preferred_skills: list[str] | None,
    job_experience_level: str | None,
    job_experience_years_range: str | None,
    job_location: str | None,
    job_posted_date: date | None,
) -> tuple[float, dict[str, Any]]:
    """
    Compute compatibility score 0-100 and match details.
    Weights: required skills 40%, preferred 20%, experience 20%, location 10%, recency 10%.
    """
    p_skills = _normalize_skills(profile_skills)
    req = _normalize_skills(job_required_skills)
    pref = _normalize_skills(job_preferred_skills)

    required_match = len(p_skills & req) / len(req) if req else 1.0
    preferred_match = len(p_skills & pref) / len(pref) if pref else 1.0

    exp_score = _experience_level_score(
        profile_experience_years,
        job_experience_level,
        job_experience_years_range,
    )
    loc_score = _location_score(profile_location, job_location)
    rec_score = _recency_score(job_posted_date)

    # Weights: required skills 40%, preferred 20%, experience 20%, location 10%, recency 10%
    total = (
        required_match * 40.0
        + preferred_match * 20.0
        + exp_score * 20.0
        + loc_score * 10.0
        + rec_score * 10.0
    )
    total = min(100.0, max(0.0, total))

    match_details = {
        "skill_match_required": round(required_match * 100, 1),
        "skill_match_preferred": round(preferred_match * 100, 1),
        "matched_required_skills": sorted(p_skills & req),
        "missing_required_skills": sorted(req - p_skills),
        "experience_score": round(exp_score * 100, 1),
        "location_score": round(loc_score * 100, 1),
        "recency_score": round(rec_score * 100, 1),
    }
    return round(total, 2), match_details
