"""
Generate personalized interview prep questions using LLM.
Mix: behavioral 40%, technical 40%, company-specific 20%.
"""
from typing import Any

from src.services.llm.base import get_openai_client, chat_completion_json, LLMServiceError
from src.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an interview coach. Generate interview preparation questions for a candidate.
Output a single JSON object with:
- "questions": array of objects, each with "question" (string), "type" (one of "behavioral", "technical", "company"), "category" (string, e.g. leadership, system design), "difficulty" (one of "easy", "medium", "hard")
- "company_insights": string (2-3 sentences about the company/role to help the candidate)
- "tips": array of strings (3-5 short tips for this interview)

Distribution: about 40% behavioral (STAR method), 40% technical (role-specific), 20% company-specific.
Generate 15-20 questions. Vary difficulty. Personalize technical questions to the job title and required skills.
Do not repeat questions."""


class InterviewGenerator:
    """Generates interview prep kits from job match and profile."""

    async def generate(
        self,
        job_title: str,
        company_name: str,
        job_description: str,
        required_skills: list[str],
        profile_skills: list[str],
        missing_skills: list[str],
    ) -> dict[str, Any]:
        """
        Generate questions, company_insights, and tips.
        Returns dict with questions, company_insights, tips.
        """
        user_content = f"""
Job title: {job_title}
Company: {company_name}
Job description (excerpt): {job_description[:3000]}

Required skills: {required_skills[:20]}
Candidate skills: {profile_skills[:20]}
Skill gaps (candidate missing): {missing_skills[:15]}

Generate 15-20 interview questions (mix behavioral, technical, company-specific), company_insights, and tips.
"""
        try:
            client = get_openai_client()
            data = await chat_completion_json(
                client,
                system_prompt=SYSTEM_PROMPT,
                user_content=user_content,
                max_tokens=2500,
            )
        except LLMServiceError:
            raise
        except Exception as e:
            logger.exception("Interview generation failed")
            raise LLMServiceError(str(e)) from e

        raw_questions = data.get("questions") or []
        if not isinstance(raw_questions, list):
            raw_questions = []
        tips = data.get("tips") or []
        if not isinstance(tips, list):
            tips = []
        # Normalize each question into a dict with required keys.
        # Reassigning loop variable doesn't mutate the list, so build a new one.
        questions: list[dict[str, str]] = []
        for item in raw_questions:
            if not isinstance(item, dict):
                item = {"question": str(item)}
            item.setdefault("question", "")
            item.setdefault("type", "technical")
            item.setdefault("category", "general")
            item.setdefault("difficulty", "medium")
            questions.append(item)
        return {
            "questions": questions[:25],
            "company_insights": data.get("company_insights") or "",
            "tips": [str(t) for t in tips][:10],
        }
