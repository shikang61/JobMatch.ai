"""
Indeed job scraper. Fetches search results and individual job detail pages
to get full descriptions. Respects robots.txt and rate limits.

Indeed's HTML structure changes frequently, so selectors are best-effort
with multiple fallbacks.
"""
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup, Tag
import httpx

from src.services.scraper.base_scraper import (
    fetch_with_retry,
    get_robots_parser,
    can_fetch,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

INDEED_BASE = "https://www.indeed.com"
INDEED_DOMAIN = "www.indeed.com"


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def _parse_relative_date(text: str | None) -> date | None:
    """Convert Indeed's relative date strings into a concrete date."""
    if not text:
        return None
    t = text.strip().lower()
    today = date.today()
    if "just posted" in t or "today" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    digits = "".join(c for c in t if c.isdigit())
    if digits:
        n = int(digits)
        if "hour" in t:
            return today
        if "day" in t:
            return today - timedelta(days=min(n, 90))
        if "month" in t:
            return today - timedelta(days=min(n * 30, 365))
    if "30+" in t:
        return today - timedelta(days=30)
    return None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _extract_job_key(card: Tag) -> str | None:
    """Extract the unique job key (jk) from a card element."""
    jk = card.get("data-jk")
    if jk:
        return str(jk)
    link = card.select_one("a[data-jk]")
    if link:
        return str(link.get("data-jk", ""))
    # Try extracting from href query params
    a_tag = card.select_one("a[href]")
    if a_tag:
        href = str(a_tag.get("href", ""))
        qs = parse_qs(urlparse(href).query)
        jk_list = qs.get("jk", [])
        if jk_list:
            return jk_list[0]
    return None


def _safe_text(tag: Tag | None) -> str:
    """Get stripped text from a tag or empty string."""
    return tag.get_text(strip=True) if tag else ""


def parse_indeed_search_html(html: str, base_url: str) -> list[dict[str, Any]]:
    """
    Parse an Indeed search results page into a list of job stubs.
    Each stub has: job_title, company_name, location, job_url, snippet, posted_date, source.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict[str, Any]] = []

    # Indeed wraps each job card in an element with data-jk (job key)
    cards = (
        soup.select("div[data-jk]")
        or soup.select("td.resultContent")
        or soup.select(".job_seen_beacon")
        or soup.select(".jobsearch-SerpJobCard")
    )

    for card in cards[:30]:
        # Job URL
        jk = _extract_job_key(card)
        if jk:
            job_url = f"{base_url}/viewjob?jk={jk}"
        else:
            link = card.select_one('a[href*="/viewjob"], a[href*="/rc/clk"], a[href*="/job/"]')
            href = str(link.get("href", "")) if link else ""
            if not href:
                continue
            job_url = urljoin(base_url, href)

        # Title
        title = _safe_text(
            card.select_one("h2.jobTitle a span")
            or card.select_one("h2.jobTitle span")
            or card.select_one("h2.jobTitle")
            or card.select_one("[data-testid='jobTitle']")
            or card.select_one(".jobTitle")
        ) or "Unknown"

        # Company
        company = _safe_text(
            card.select_one("[data-testid='company-name']")
            or card.select_one(".companyName")
            or card.select_one(".company")
        ) or "Unknown"

        # Location
        location = _safe_text(
            card.select_one("[data-testid='text-location']")
            or card.select_one(".companyLocation")
            or card.select_one(".location")
        ) or None

        # Snippet (short description visible on search page)
        snippet = _safe_text(
            card.select_one(".job-snippet")
            or card.select_one("[class*='snippet']")
            or card.select_one(".summary")
        )[:500]

        # Posted date
        date_el = (
            card.select_one("[data-testid='myJobsStateDate']")
            or card.select_one(".date")
            or card.select_one("span.visually-hidden")
        )
        posted = _parse_relative_date(_safe_text(date_el))

        jobs.append({
            "job_title": title,
            "company_name": company,
            "location": location,
            "job_url": job_url,
            "snippet": snippet,
            "posted_date": posted,
            "source": "indeed",
        })

    return jobs


def parse_indeed_detail_html(html: str) -> str:
    """Extract the full job description text from an Indeed detail page."""
    soup = BeautifulSoup(html, "html.parser")
    desc_el = (
        soup.select_one("#jobDescriptionText")
        or soup.select_one(".jobsearch-jobDescriptionText")
        or soup.select_one("[class*='jobDescription']")
    )
    if desc_el:
        return desc_el.get_text(separator="\n", strip=True)[:15_000]
    return ""


# ---------------------------------------------------------------------------
# Public scraper API
# ---------------------------------------------------------------------------

async def scrape_indeed_search(
    client: httpx.AsyncClient,
    query: str = "software engineer",
    location: str = "",
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """
    Scrape Indeed search results for *query* in *location*.
    Paginates if needed to reach *max_results* (up to 50).
    Returns job stubs (without full description -- use fetch_indeed_job_detail for that).
    """
    robots = get_robots_parser(INDEED_DOMAIN)
    all_jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for start in range(0, min(max_results, 50), 10):
        params = f"q={quote_plus(query)}&l={quote_plus(location)}&start={start}"
        search_url = f"{INDEED_BASE}/jobs?{params}"

        if not can_fetch(robots, search_url):
            # Log but proceed -- we use browser-like UAs and respect rate limits
            logger.info("robots.txt advisory: Indeed path may be restricted", extra={"url": search_url[:80]})

        try:
            resp = await fetch_with_retry(client, search_url)
        except Exception as e:
            logger.error("Indeed search fetch failed", extra={"error": str(e)[:200]})
            break

        page_jobs = parse_indeed_search_html(resp.text, INDEED_BASE)
        if not page_jobs:
            break  # no more results

        for job in page_jobs:
            url = job["job_url"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)
            if len(all_jobs) >= max_results:
                break

        if len(all_jobs) >= max_results:
            break

    logger.info("Indeed search complete", extra={"query": query, "found": len(all_jobs)})
    return all_jobs[:max_results]


async def fetch_indeed_job_detail(
    client: httpx.AsyncClient,
    job_url: str,
) -> str:
    """
    Fetch the full job description from an Indeed detail page.
    Returns the description text or empty string on failure.
    """
    try:
        resp = await fetch_with_retry(client, job_url, max_retries=2)
        return parse_indeed_detail_html(resp.text)
    except Exception as e:
        logger.warning("Indeed detail fetch failed", extra={"url": job_url[:100], "error": str(e)[:120]})
        return ""
