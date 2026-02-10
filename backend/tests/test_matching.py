"""Unit tests for matching algorithm."""
from datetime import date, timedelta

from src.services.matching.job_matcher import compute_match_score


def test_matching_score_full_match():
    score, details = compute_match_score(
        profile_skills=["Python", "PostgreSQL", "AWS"],
        profile_experience_years=5,
        profile_location=None,
        job_required_skills=["Python", "PostgreSQL"],
        job_preferred_skills=["AWS"],
        job_experience_level="senior",
        job_experience_years_range="5-7",
        job_location=None,
        job_posted_date=date.today() - timedelta(days=2),
    )
    assert score >= 80
    assert "skill_match_required" in details
    assert details["skill_match_required"] == 100.0


def test_matching_score_no_skills_overlap():
    score, details = compute_match_score(
        profile_skills=["Java", "Kotlin"],
        profile_experience_years=2,
        profile_location=None,
        job_required_skills=["Python", "Go"],
        job_preferred_skills=[],
        job_experience_level="mid",
        job_experience_years_range="2-4",
        job_location=None,
        job_posted_date=date.today(),
    )
    assert score < 70
    assert sorted(details.get("missing_required_skills", [])) == ["go", "python"]
