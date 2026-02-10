"""
Deep research scraper: uses LLM to identify top companies for a role,
then scrapes each company's job openings from LinkedIn.

Yields progress events as async generator for SSE streaming.
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.job import Job
from src.services.llm.base import get_openai_client, chat_completion_json, LLMServiceError
from src.services.scraper.base_scraper import build_httpx_client
from src.services.scraper.linkedin_scraper import (
    scrape_linkedin_search,
    fetch_linkedin_job_detail,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

COMPANY_RESEARCH_PROMPT = """You are a career research analyst. Given a job role and optional location,
identify the top companies that are excellent employers for this role.

Consider:
- Companies known for strong engineering/professional culture
- Market leaders and well-funded startups in relevant industries
- Companies actively hiring for this type of role
- Mix of large enterprises, mid-size companies, and promising startups
- If a location is specified, prioritize companies with presence there

Respond with a single JSON object:
{
  "companies": [
    {
      "name": "Company Name",
      "reason": "Brief reason why this is a good company for this role (1 sentence)",
      "industry": "e.g. Tech, Finance, Healthcare"
    }
  ]
}

Return 8-12 companies. Use well-known, real company names only."""


@dataclass
class CompanyInfo:
    name: str
    reason: str
    industry: str


@dataclass
class CompanySearchResult:
    company: CompanyInfo
    jobs_found: int = 0
    jobs_new: int = 0
    status: str = "pending"  # pending, searching, done, error
    error: str | None = None


@dataclass
class DeepResearchProgress:
    """A single progress event to stream to the client."""
    event: str  # research_start, companies_found, searching_company, company_done, job_saved, complete, error
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        payload = json.dumps(self.data, default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"


async def _research_companies(role: str, location: str) -> list[CompanyInfo]:
    """Use LLM to identify top companies for a role."""
    user_content = f"Role: {role}"
    if location:
        user_content += f"\nPreferred location: {location}"

    client = get_openai_client()
    data = await chat_completion_json(
        client,
        system_prompt=COMPANY_RESEARCH_PROMPT,
        user_content=user_content,
        max_tokens=1500,
    )

    raw = data.get("companies") or []
    if not isinstance(raw, list):
        return []

    companies: list[CompanyInfo] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            companies.append(CompanyInfo(
                name=str(item["name"]).strip(),
                reason=str(item.get("reason", "")).strip(),
                industry=str(item.get("industry", "")).strip(),
            ))
    return companies[:15]


async def _get_existing_urls(db: AsyncSession) -> set[str]:
    """Load existing job URLs for dedup."""
    result = await db.execute(select(Job.job_url).where(Job.job_url.isnot(None)))
    return {row[0] for row in result.all() if row[0]}


async def run_deep_research(
    db: AsyncSession,
    role: str,
    location: str = "",
    max_jobs_per_company: int = 5,
    fetch_details: bool = True,
) -> AsyncGenerator[DeepResearchProgress, None]:
    """
    Async generator that yields progress events:
    1. research_start - LLM is researching companies
    2. companies_found - list of companies identified
    3. searching_company - starting search for a specific company
    4. company_done - finished searching a company (with results)
    5. job_saved - a new job was saved
    6. complete - all done with summary
    7. error - something went wrong

    The caller should iterate this and stream each event as SSE.
    """
    # Phase 1: Research companies
    yield DeepResearchProgress(
        event="research_start",
        data={"message": f"Researching top companies for: {role}", "role": role, "location": location},
    )

    try:
        companies = await _research_companies(role, location)
    except LLMServiceError as e:
        yield DeepResearchProgress(event="error", data={"message": f"Research failed: {str(e)[:200]}"})
        return
    except Exception as e:
        yield DeepResearchProgress(event="error", data={"message": f"Unexpected error: {str(e)[:200]}"})
        return

    if not companies:
        yield DeepResearchProgress(event="error", data={"message": "Could not identify companies. Try a different role."})
        return

    yield DeepResearchProgress(
        event="companies_found",
        data={
            "count": len(companies),
            "companies": [
                {"name": c.name, "reason": c.reason, "industry": c.industry}
                for c in companies
            ],
        },
    )

    # Phase 2: Search each company on LinkedIn
    existing_urls = await _get_existing_urls(db)
    total_new = 0
    company_results: list[dict[str, Any]] = []

    async with build_httpx_client() as http_client:
        for i, company in enumerate(companies):
            yield DeepResearchProgress(
                event="searching_company",
                data={
                    "index": i,
                    "total": len(companies),
                    "company": company.name,
                    "industry": company.industry,
                    "reason": company.reason,
                },
            )

            search_query = f"{role} {company.name}"
            try:
                stubs = await scrape_linkedin_search(
                    http_client,
                    query=search_query,
                    location=location,
                    max_results=max_jobs_per_company,
                )
            except Exception as e:
                logger.warning("Company search failed", extra={"company": company.name, "error": str(e)[:120]})
                yield DeepResearchProgress(
                    event="company_done",
                    data={
                        "company": company.name,
                        "found": 0,
                        "new": 0,
                        "status": "error",
                        "error": str(e)[:100],
                    },
                )
                company_results.append({"company": company.name, "found": 0, "new": 0, "status": "error"})
                continue

            company_new = 0
            for stub in stubs:
                url = stub.get("job_url", "")
                if url in existing_urls:
                    continue

                # Fetch full description
                description = ""
                if fetch_details and stub.get("job_id"):
                    try:
                        description = await fetch_linkedin_job_detail(http_client, stub["job_id"])
                    except Exception:
                        pass

                if not description:
                    description = stub.get("snippet") or ""

                job = Job(
                    company_name=stub.get("company_name") or company.name,
                    job_title=stub.get("job_title") or "Unknown",
                    job_description=description,
                    required_skills=[],
                    preferred_skills=[],
                    location=stub.get("location"),
                    job_url=url,
                    source="deep_research",
                    posted_date=stub.get("posted_date"),
                    is_active=True,
                )
                db.add(job)
                existing_urls.add(url)
                company_new += 1
                total_new += 1

            if company_new > 0:
                await db.flush()

            yield DeepResearchProgress(
                event="company_done",
                data={
                    "company": company.name,
                    "found": len(stubs),
                    "new": company_new,
                    "status": "done",
                },
            )
            company_results.append({
                "company": company.name,
                "found": len(stubs),
                "new": company_new,
                "status": "done",
            })

    # Phase 3: Complete
    yield DeepResearchProgress(
        event="complete",
        data={
            "total_new": total_new,
            "companies_searched": len(companies),
            "results": company_results,
        },
    )
