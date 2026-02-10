"""
LLM-powered job description analysis. Extracts skills, level, responsibilities.
"""
from typing import Any

from src.services.llm.base import get_openai_client, chat_completion_json, LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a job description analyzer. Extract structured data from the given job posting text.
Respond with a single JSON object with these exact keys:
- "required_skills": array of strings (technologies, tools; normalize)
- "preferred_skills": array of strings (nice-to-have)
- "experience_level": one of "entry", "mid", "senior", "lead", "executive", or null
- "experience_years": string like "2-4" or "5+" or null
- "key_responsibilities": array of strings (short phrases)
- "company_size": one of "startup", "mid", "enterprise", or null

Do not invent. Use null or empty array when unclear. Keep required_skills and preferred_skills concise (max 25 each)."""


class JobAnalyzer:
    """Analyzes job description text and returns structured data."""

    async def analyze_job_description(self, description: str) -> dict[str, Any]:
        """
        Parse job description into structured data using LLM.
        Returns dict with required_skills, preferred_skills, experience_level, etc.
        """
        if not description or len(description.strip()) < 20:
            return {
                "required_skills": [],
                "preferred_skills": [],
                "experience_level": None,
                "experience_years": None,
                "key_responsibilities": [],
                "company_size": None,
            }
        try:
            client = get_openai_client()
            data = await chat_completion_json(
                client,
                system_prompt=SYSTEM_PROMPT,
                user_content=description[:12000],
                max_tokens=1000,
            )
            required = data.get("required_skills") or []
            preferred = data.get("preferred_skills") or []
            if not isinstance(required, list):
                required = []
            if not isinstance(preferred, list):
                preferred = []
            responsibilities = data.get("key_responsibilities") or []
            if not isinstance(responsibilities, list):
                responsibilities = []
            return {
                "required_skills": [str(s).strip() for s in required if s][:30],
                "preferred_skills": [str(s).strip() for s in preferred if s][:20],
                "experience_level": data.get("experience_level") or None,
                "experience_years": data.get("experience_years") or None,
                "key_responsibilities": [str(r).strip() for r in responsibilities if r][:15],
                "company_size": data.get("company_size") or None,
            }
        except LLMServiceError:
            raise
        except Exception as e:
            logger.exception("Job analysis failed")
            raise LLMServiceError(str(e)) from e

    async def summarize_for_candidate(
        self, job_title: str, company_name: str, description: str
    ) -> dict[str, Any]:
        """
        Summarise job description: key skills, qualifications, cultural fit,
        advantageous skills. For candidate prep.
        """
        if not description or len(description.strip()) < 20:
            return {
                "key_skills": [],
                "qualifications": [],
                "cultural_fit": "",
                "advantageous_skills": [],
                "expected_salary": "",
                "industry": "",
            }
        system = """You are a career coach. Summarise the job posting for a candidate.
Respond with a single JSON object:
- "key_skills": array of strings (main skills/technologies they look for)
- "qualifications": array of strings (education, certs, must-have experience)
- "cultural_fit": string (2-4 sentences on company culture, values, work style)
- "advantageous_skills": array of strings (nice-to-have, "plus", "preferred" skills)
- "expected_salary": string (salary range or compensation if mentioned, e.g. "$120k–$150k", "£50k-65k", "Competitive". If not mentioned use empty string "")
- "industry": string (single word or short phrase, e.g. "Technology", "Healthcare", "Finance", "E-commerce". Infer from company and role.)

Be concise. Use the employer's wording where possible. No fluff."""
        user = f"Company: {company_name}\nRole: {job_title}\n\nDescription:\n{description[:8000]}"
        try:
            client = get_openai_client()
            data = await chat_completion_json(
                client,
                system_prompt=system,
                user_content=user,
                max_tokens=800,
            )
            key_skills = data.get("key_skills") or []
            qualifications = data.get("qualifications") or []
            cultural_fit = data.get("cultural_fit") or ""
            advantageous_skills = data.get("advantageous_skills") or []
            expected_salary = data.get("expected_salary") or ""
            industry = data.get("industry") or ""
            if not isinstance(key_skills, list):
                key_skills = []
            if not isinstance(qualifications, list):
                qualifications = []
            if not isinstance(advantageous_skills, list):
                advantageous_skills = []
            return {
                "key_skills": [str(s).strip() for s in key_skills if s][:20],
                "qualifications": [str(q).strip() for q in qualifications if q][:15],
                "cultural_fit": str(cultural_fit).strip()[:1500],
                "advantageous_skills": [str(s).strip() for s in advantageous_skills if s][:15],
                "expected_salary": str(expected_salary).strip()[:200],
                "industry": str(industry).strip()[:100],
            }
        except LLMServiceError:
            raise
        except Exception as e:
            logger.exception("Job summary failed")
            raise LLMServiceError(str(e)) from e
