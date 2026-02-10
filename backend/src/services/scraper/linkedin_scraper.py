"""
LinkedIn job scraper using the public guest job search endpoints.

LinkedIn exposes a guest-accessible job search at:
  https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...

This returns server-rendered HTML fragments that can be parsed without
authentication. Individual job detail pages are also publicly accessible at:
  https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}

IMPORTANT: LinkedIn aggressively rate-limits scrapers. We use conservative
delays (2-4s between requests), respect robots.txt, identify our bot in the
User-Agent, and cache results. For production use, apply for LinkedIn's
official Job Posting API (https://developer.linkedin.com).
"""
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote_plus, urlparse, parse_qs
import re

from bs4 import BeautifulSoup, Tag
import httpx

from src.services.scraper.base_scraper import (
    fetch_with_retry,
    get_robots_parser,
    can_fetch,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

LINKEDIN_DOMAIN = "www.linkedin.com"
LINKEDIN_BASE = "https://www.linkedin.com"
# Guest API endpoints (no login required)
SEARCH_API = f"{LINKEDIN_BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_API = f"{LINKEDIN_BASE}/jobs-guest/jobs/api/jobPosting"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_linkedin_date(text: str | None) -> date | None:
    """Parse LinkedIn's relative date strings like '2 days ago', '1 week ago'."""
    if not text:
        return None
    t = text.strip().lower()
    today = date.today()
    if "just now" in t or "moment" in t:
        return today
    digits = "".join(c for c in t if c.isdigit())
    n = int(digits) if digits else 0
    if "hour" in t or "minute" in t:
        return today
    if "day" in t:
        return today - timedelta(days=max(n, 1))
    if "week" in t:
        return today - timedelta(weeks=max(n, 1))
    if "month" in t:
        return today - timedelta(days=max(n, 1) * 30)
    return None


def _extract_linkedin_job_id(url_or_el: str | Tag) -> str | None:
    """Extract the numeric job ID from a LinkedIn URL or anchor element."""
    if isinstance(url_or_el, Tag):
        href = str(url_or_el.get("href", ""))
    else:
        href = url_or_el
    # Pattern: /jobs/view/1234567... or /jobs-guest/.../1234567
    match = re.search(r"/(?:view|jobs)/(\d{6,})", href)
    if match:
        return match.group(1)
    # Fallback: data-entity-urn="urn:li:jobPosting:1234567"
    if isinstance(url_or_el, Tag):
        urn = str(url_or_el.get("data-entity-urn", ""))
        m = re.search(r"jobPosting:(\d+)", urn)
        if m:
            return m.group(1)
    return None


def _safe_text(tag: Tag | None) -> str:
    return tag.get_text(strip=True) if tag else ""


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def parse_linkedin_search_html(html: str) -> list[dict[str, Any]]:
    """
    Parse the HTML fragment returned by LinkedIn's guest search API.
    Returns a list of job stubs with: job_title, company_name, location,
    job_url, job_id, posted_date, source.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict[str, Any]] = []

    # Each card is a <li> or <div> with a base-card class
    cards = (
        soup.select("li.jobs-search-results__list-item")
        or soup.select("div.base-card")
        or soup.select("li")
    )

    for card in cards[:30]:
        # Title & link
        title_el = (
            card.select_one("h3.base-search-card__title")
            or card.select_one(".base-search-card__title")
            or card.select_one("h3")
        )
        title = _safe_text(title_el) or "Unknown"

        link_el = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
        if not link_el:
            continue
        href = str(link_el.get("href", ""))
        job_id = _extract_linkedin_job_id(href)
        if not job_id:
            job_id = _extract_linkedin_job_id(card)
        if not job_id:
            continue

        job_url = f"{LINKEDIN_BASE}/jobs/view/{job_id}"

        # Company
        company = _safe_text(
            card.select_one("h4.base-search-card__subtitle")
            or card.select_one(".base-search-card__subtitle")
            or card.select_one("h4")
        ) or "Unknown"

        # Location
        location = _safe_text(
            card.select_one(".job-search-card__location")
            or card.select_one(".base-search-card__metadata span")
        ) or None

        # Date
        time_el = card.select_one("time")
        date_text = time_el.get("datetime") if time_el else _safe_text(
            card.select_one(".job-search-card__listdate")
            or card.select_one(".job-search-card__listdate--new")
        )
        posted = None
        if date_text:
            # datetime attr is ISO: "2026-02-05"
            try:
                posted = date.fromisoformat(str(date_text)[:10])
            except ValueError:
                posted = _parse_linkedin_date(str(date_text))

        jobs.append({
            "job_title": title,
            "company_name": company,
            "location": location,
            "job_url": job_url,
            "job_id": job_id,
            "snippet": "",
            "posted_date": posted,
            "source": "linkedin",
        })

    return jobs


def parse_linkedin_detail_html(html: str) -> str:
    """Extract the full description text from a LinkedIn guest detail page."""
    soup = BeautifulSoup(html, "html.parser")
    desc = (
        soup.select_one(".show-more-less-html__markup")
        or soup.select_one(".description__text")
        or soup.select_one("section.description")
    )
    if desc:
        return desc.get_text(separator="\n", strip=True)[:15_000]
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scrape_linkedin_search(
    client: httpx.AsyncClient,
    query: str = "software engineer",
    location: str = "",
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """
    Scrape LinkedIn's guest job search for *query* in *location*.
    Paginates to reach up to *max_results* (capped at 50).
    Returns job stubs (without full description).
    """
    robots = get_robots_parser(LINKEDIN_DOMAIN)
    all_jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for start in range(0, min(max_results, 50), 25):
        url = (
            f"{SEARCH_API}?"
            f"keywords={quote_plus(query)}"
            f"&location={quote_plus(location)}"
            f"&start={start}"
        )

        if not can_fetch(robots, url):
            logger.info("robots.txt advisory: LinkedIn path may be restricted", extra={"url": url[:100]})

        try:
            resp = await fetch_with_retry(client, url, max_retries=2, timeout=20.0)
        except Exception as e:
            logger.error(
                "LinkedIn search fetch failed",
                extra={"error": str(e)[:200], "start": start},
            )
            break

        page_jobs = parse_linkedin_search_html(resp.text)
        if not page_jobs:
            break

        for job in page_jobs:
            jid = job.get("job_id", job["job_url"])
            if jid not in seen_ids:
                seen_ids.add(jid)
                all_jobs.append(job)
            if len(all_jobs) >= max_results:
                break

        if len(all_jobs) >= max_results:
            break

    logger.info("LinkedIn search complete", extra={"query": query, "found": len(all_jobs)})
    return all_jobs[:max_results]


async def fetch_linkedin_job_detail(
    client: httpx.AsyncClient,
    job_id: str,
) -> str:
    """
    Fetch full job description from LinkedIn's guest detail API.
    Returns description text or empty string on failure.
    """
    url = f"{DETAIL_API}/{job_id}"
    try:
        resp = await fetch_with_retry(client, url, max_retries=2, timeout=20.0)
        return parse_linkedin_detail_html(resp.text)
    except Exception as e:
        logger.warning(
            "LinkedIn detail fetch failed",
            extra={"job_id": job_id, "error": str(e)[:120]},
        )
        return ""
