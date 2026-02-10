"""
LLM-powered CV/profile analysis. Extracts skills with competency levels,
experience, education, and suggests relevant job titles for searching.
"""
from typing import Any

from src.services.llm.base import get_openai_client, chat_completion_json, LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a CV parser and career advisor. Extract structured data from the given CV/resume text.
Respond with a single JSON object with these exact keys:

- "full_name": string or null
- "skills": array of strings (technologies, languages, tools; normalize casing)
- "skill_competencies": array of objects, each with:
    - "skill": string (same skill names as in "skills")
    - "level": integer 1-5 (1=beginner, 2=basic, 3=intermediate, 4=advanced, 5=expert)
  Infer the level from context: years of usage, project complexity, certifications, job titles.
  If unclear, default to 3 (intermediate).
- "experience": array of objects, each with "company", "role", "duration" (e.g. "2 years")
- "education": array of strings (degree and institution)
- "total_years_experience": number (integer, 0 if not clear)
- "suggested_job_titles": array of 5-8 strings — relevant job titles this candidate
  should search for based on their skills and experience. Be specific (e.g. "Senior Python
  Backend Engineer", "Full Stack Developer", "Data Engineer"). Mix seniority levels
  around their experience level.

Do not invent information about the candidate. Use null or empty array if not found.
Keep skills list concise (max 30). For skill_competencies, include the top 15 skills."""


class ProfileAnalyzer:
    """Analyzes CV text and returns structured profile data with competency levels."""

    async def analyze_cv_text(self, cv_text: str) -> dict[str, Any]:
        """
        Parse CV text into structured data using LLM.
        Returns dict with full_name, skills, skill_competencies, experience,
        education, total_years_experience, suggested_job_titles.
        """
        if not cv_text or len(cv_text.strip()) < 50:
            return {
                "full_name": None,
                "skills": [],
                "skill_competencies": [],
                "experience": [],
                "education": [],
                "total_years_experience": 0,
                "suggested_job_titles": [],
            }
        try:
            client = get_openai_client()
            data = await chat_completion_json(
                client,
                system_prompt=SYSTEM_PROMPT,
                user_content=cv_text[:15000],
                max_tokens=2000,
            )

            # Normalize skills (flat list of strings)
            skills = data.get("skills") or []
            if not isinstance(skills, list):
                skills = []

            # Normalize skill competencies
            raw_comps = data.get("skill_competencies") or []
            if not isinstance(raw_comps, list):
                raw_comps = []
            skill_competencies: list[dict[str, Any]] = []
            for item in raw_comps:
                if isinstance(item, dict) and "skill" in item:
                    level = item.get("level", 3)
                    if not isinstance(level, int) or level < 1 or level > 5:
                        level = 3
                    skill_competencies.append({
                        "skill": str(item["skill"]).strip(),
                        "level": level,
                    })

            # Normalize experience
            experience = data.get("experience") or []
            if not isinstance(experience, list):
                experience = []

            # Normalize education
            education = data.get("education") or []
            if not isinstance(education, list):
                education = []

            # Years of experience
            years = data.get("total_years_experience")
            if years is None or not isinstance(years, (int, float)):
                years = 0

            # Suggested job titles
            raw_titles = data.get("suggested_job_titles") or []
            if not isinstance(raw_titles, list):
                raw_titles = []
            suggested_job_titles = [str(t).strip() for t in raw_titles if t][:10]

            return {
                "full_name": data.get("full_name"),
                "skills": [str(s).strip() for s in skills if s][:50],
                "skill_competencies": skill_competencies[:20],
                "experience": experience[:20],
                "education": education[:10],
                "total_years_experience": max(0, int(years)),
                "suggested_job_titles": suggested_job_titles,
            }
        except LLMServiceError:
            raise
        except Exception as e:
            logger.exception("Profile analysis failed")
            raise LLMServiceError(str(e)) from e
