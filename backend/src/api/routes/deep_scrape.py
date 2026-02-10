"""
Deep research scrape: LLM identifies top companies for a role, then
scrapes each company's openings on LinkedIn. Streams progress via SSE.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.config import get_settings
from src.database.connection import get_db
from src.services.scraper.deep_research import run_deep_research
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class DeepScrapeRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=200, description="Job role to research")
    location: str = Field(default="", max_length=200, description="Preferred location")
    max_jobs_per_company: int = Field(default=5, ge=1, le=15)
    fetch_details: bool = Field(default=True)


@router.post("/deep-scrape")
async def deep_scrape(
    user_id: CurrentUserId,
    request: Request,
    body: DeepScrapeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Deep research + scrape. Uses LLM to identify top companies for the role,
    then searches each company's openings on LinkedIn.

    Returns a Server-Sent Events (SSE) stream with live progress.

    Events:
    - research_start: LLM is analyzing best companies
    - companies_found: list of identified companies
    - searching_company: currently searching a specific company
    - company_done: finished a company (with found/new counts)
    - complete: all done with summary
    - error: something went wrong
    """
    check_api_rate_limit(request, user_id)

    settings = get_settings()
    if not settings.scraping_enabled:
        raise HTTPException(status_code=400, detail="Scraping is disabled.")
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not configured (needed for company research).")

    logger.info("Deep scrape started", extra={"user_id": user_id[:8], "role": body.role, "location": body.location})

    async def event_stream():
        """Async generator that yields SSE-formatted strings."""
        try:
            async for progress in run_deep_research(
                db,
                role=body.role,
                location=body.location,
                max_jobs_per_company=body.max_jobs_per_company,
                fetch_details=body.fetch_details,
            ):
                yield progress.to_sse()

            # Commit all new jobs after the stream completes successfully
            await db.commit()
        except Exception as e:
            logger.exception("Deep scrape stream error")
            import json
            error_data = json.dumps({"message": f"Stream error: {str(e)[:200]}"})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
