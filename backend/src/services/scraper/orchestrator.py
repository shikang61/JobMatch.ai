"""
Scraper orchestrator: coordinates scraping from multiple sources,
deduplicates by job_url, persists to the database, and optionally
enriches sparse listings with full descriptions from detail pages.

Usage from an API route:

    result = await run_scrape(db, query="python developer", location="Remote")
"""
import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.job import Job
from src.services.scraper.base_scraper import build_httpx_client
from src.services.scraper.indeed_scraper import (
    scrape_indeed_search,
    fetch_indeed_job_detail,
)
from src.services.scraper.linkedin_scraper import (
    scrape_linkedin_search,
    fetch_linkedin_job_detail,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScrapeResult:
    """Summary of a scraping run."""
    source: str
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_skipped_duplicate: int = 0
    jobs_enriched: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ScrapeReport:
    """Aggregated report across all sources."""
    results: list[ScrapeResult] = field(default_factory=list)
    total_new: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_new": self.total_new,
            "sources": [
                {
                    "source": r.source,
                    "found": r.jobs_found,
                    "new": r.jobs_new,
                    "duplicates": r.jobs_skipped_duplicate,
                    "enriched": r.jobs_enriched,
                    "errors": r.errors[:5],
                }
                for r in self.results
            ],
        }


async def _get_existing_urls(db: AsyncSession) -> set[str]:
    """Load all known job_url values from the DB to deduplicate cheaply."""
    result = await db.execute(select(Job.job_url).where(Job.job_url.isnot(None)))
    return {row[0] for row in result.all() if row[0]}


def _stub_to_job(stub: dict[str, Any], description: str) -> Job:
    """Convert a scraper stub dict + full description into a Job model instance."""
    return Job(
        company_name=stub.get("company_name") or "Unknown",
        job_title=stub.get("job_title") or "Unknown",
        job_description=description or stub.get("snippet") or "",
        required_skills=[],  # will be populated by LLM analysis later
        preferred_skills=[],
        location=stub.get("location"),
        job_url=stub.get("job_url"),
        source=stub.get("source"),
        posted_date=stub.get("posted_date"),
        is_active=True,
    )


async def _scrape_source_indeed(
    query: str,
    location: str,
    max_results: int,
    existing_urls: set[str],
    db: AsyncSession,
    fetch_details: bool,
) -> ScrapeResult:
    """Scrape Indeed, fetch details, persist new jobs."""
    result = ScrapeResult(source="indeed")
    async with build_httpx_client() as client:
        try:
            stubs = await scrape_indeed_search(client, query, location, max_results)
        except Exception as e:
            result.errors.append(f"Search failed: {str(e)[:200]}")
            return result

        result.jobs_found = len(stubs)

        for stub in stubs:
            url = stub.get("job_url", "")
            if url in existing_urls:
                result.jobs_skipped_duplicate += 1
                continue

            # Fetch full description from detail page
            description = ""
            if fetch_details and url:
                try:
                    description = await fetch_indeed_job_detail(client, url)
                    if description:
                        result.jobs_enriched += 1
                except Exception as e:
                    result.errors.append(f"Detail fetch: {str(e)[:100]}")

            if not description:
                description = stub.get("snippet") or ""

            # Only save if we have at least some content
            if len(description.strip()) < 20 and not stub.get("job_title"):
                continue

            job = _stub_to_job(stub, description)
            db.add(job)
            existing_urls.add(url)  # prevent duplicates within the same run
            result.jobs_new += 1

    return result


async def _scrape_source_linkedin(
    query: str,
    location: str,
    max_results: int,
    existing_urls: set[str],
    db: AsyncSession,
    fetch_details: bool,
) -> ScrapeResult:
    """Scrape LinkedIn, fetch details, persist new jobs."""
    result = ScrapeResult(source="linkedin")
    async with build_httpx_client() as client:
        try:
            stubs = await scrape_linkedin_search(client, query, location, max_results)
        except Exception as e:
            result.errors.append(f"Search failed: {str(e)[:200]}")
            return result

        result.jobs_found = len(stubs)

        for stub in stubs:
            url = stub.get("job_url", "")
            if url in existing_urls:
                result.jobs_skipped_duplicate += 1
                continue

            description = ""
            if fetch_details and stub.get("job_id"):
                try:
                    description = await fetch_linkedin_job_detail(client, stub["job_id"])
                    if description:
                        result.jobs_enriched += 1
                except Exception as e:
                    result.errors.append(f"Detail fetch: {str(e)[:100]}")

            if not description:
                description = stub.get("snippet") or ""

            if len(description.strip()) < 20 and not stub.get("job_title"):
                continue

            job = _stub_to_job(stub, description)
            db.add(job)
            existing_urls.add(url)
            result.jobs_new += 1

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_scrape(
    db: AsyncSession,
    *,
    query: str = "software engineer",
    location: str = "",
    sources: list[str] | None = None,
    max_per_source: int = 25,
    fetch_details: bool = True,
) -> ScrapeReport:
    """
    Run a full scrape across requested sources.

    Args:
        db: Active async database session (caller must commit after).
        query: Job search keywords.
        location: City / "Remote" / empty for all.
        sources: List of source names to scrape. Defaults to ["indeed", "linkedin"].
        max_per_source: Max jobs to fetch per source.
        fetch_details: Whether to fetch full descriptions from detail pages.

    Returns:
        ScrapeReport with per-source stats and total new jobs.
    """
    settings = get_settings()
    if not settings.scraping_enabled:
        logger.info("Scraping is disabled in config")
        return ScrapeReport()

    if sources is None:
        sources = ["indeed", "linkedin"]

    existing_urls = await _get_existing_urls(db)
    report = ScrapeReport()

    for source in sources:
        if source == "indeed":
            sr = await _scrape_source_indeed(
                query, location, max_per_source, existing_urls, db, fetch_details,
            )
        elif source == "linkedin":
            sr = await _scrape_source_linkedin(
                query, location, max_per_source, existing_urls, db, fetch_details,
            )
        else:
            logger.warning("Unknown scraper source", extra={"source": source})
            continue
        report.results.append(sr)
        report.total_new += sr.jobs_new

    if report.total_new > 0:
        await db.flush()

    logger.info(
        "Scrape run complete",
        extra={"total_new": report.total_new, "query": query, "location": location},
    )
    return report
