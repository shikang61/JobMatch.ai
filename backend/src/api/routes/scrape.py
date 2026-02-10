"""
Scrape: trigger a job scraping run from Indeed and/or LinkedIn.
Authenticated endpoint. Rate limited to prevent abuse.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.config import get_settings
from src.database.connection import get_db
from src.services.scraper.orchestrator import run_scrape
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ScrapeRequest(BaseModel):
    """Parameters for a scrape run."""
    query: str = Field(default="software engineer", max_length=200, description="Search keywords")
    location: str = Field(default="", max_length=200, description="City, state, or 'Remote'")
    sources: list[str] = Field(
        default=["indeed", "linkedin"],
        description="Sources to scrape: 'indeed', 'linkedin'",
    )
    max_per_source: int = Field(default=15, ge=1, le=50, description="Max jobs per source")
    fetch_details: bool = Field(default=True, description="Fetch full descriptions from detail pages")


class ScrapeSourceResult(BaseModel):
    source: str
    found: int
    new: int
    duplicates: int
    enriched: int
    errors: list[str]


class ScrapeResponse(BaseModel):
    total_new: int
    sources: list[ScrapeSourceResult]


@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(
    user_id: CurrentUserId,
    request: Request,
    body: ScrapeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a job scraping run across Indeed and/or LinkedIn.
    Scrapes search results, fetches full descriptions, deduplicates,
    and saves new jobs to the database.

    Rate limited. Requires authentication.
    """
    check_api_rate_limit(request, user_id)

    settings = get_settings()
    if not settings.scraping_enabled:
        raise HTTPException(status_code=400, detail="Scraping is disabled in configuration.")

    # Validate sources
    valid_sources = {"indeed", "linkedin"}
    requested = [s.lower().strip() for s in body.sources if s.strip()]
    invalid = set(requested) - valid_sources
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sources: {', '.join(invalid)}. Valid: indeed, linkedin",
        )
    if not requested:
        requested = list(valid_sources)

    logger.info(
        "Scrape triggered",
        extra={
            "user_id": user_id[:8],
            "query": body.query,
            "location": body.location,
            "sources": requested,
        },
    )

    try:
        report = await run_scrape(
            db,
            query=body.query,
            location=body.location,
            sources=requested,
            max_per_source=body.max_per_source,
            fetch_details=body.fetch_details,
        )
    except Exception as e:
        logger.exception("Scrape run failed")
        raise HTTPException(status_code=500, detail="Scrape failed. Check server logs.") from e

    # Commit is handled by get_db dependency on success
    return ScrapeResponse(
        total_new=report.total_new,
        sources=[
            ScrapeSourceResult(
                source=r.source,
                found=r.jobs_found,
                new=r.jobs_new,
                duplicates=r.jobs_skipped_duplicate,
                enriched=r.jobs_enriched,
                errors=r.errors[:5],
            )
            for r in report.results
        ],
    )
