"""
Base scraper utilities: robots.txt checking, rate limiting, retries,
rotating user agents. All scrapers share these primitives.
"""
import asyncio
import random
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Identify the bot honestly, plus rotate realistic browser UAs for resilience
USER_AGENTS = [
    "Mozilla/5.0 (compatible; JobMatchBot/1.0; +https://jobmatch.example.com/bot)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Cache parsed robots.txt per domain for the lifetime of the process
_robots_cache: dict[str, RobotFileParser] = {}


def get_robots_parser(domain: str) -> RobotFileParser:
    """Fetch and parse robots.txt for a domain (cached in memory)."""
    if domain in _robots_cache:
        return _robots_cache[domain]

    base = f"https://{domain}" if not domain.startswith("http") else domain
    parsed = urlparse(base)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception as e:
        logger.warning(
            "Could not fetch robots.txt",
            extra={"url": robots_url, "error": str(e)[:120]},
        )
    _robots_cache[domain] = rp
    return rp


def can_fetch(robots: RobotFileParser, url: str, user_agent: str = "*") -> bool:
    """
    Return True if robots.txt allows fetching *url* for the given user-agent.
    Default agent is "*" (the wildcard rules) since we use browser-like UAs.
    We still won't scrape paths that are blocked for all agents.
    """
    try:
        return robots.can_fetch(user_agent, url)
    except Exception:
        return True  # fail-open if robots parser itself errors


async def rate_limit_delay() -> None:
    """Sleep for a configured delay to respect per-domain rate limits."""
    settings = get_settings()
    base_delay = 1.0 / max(0.5, settings.scraping_rate_limit_per_second)
    jitter = random.uniform(
        settings.scraping_request_delay_min,
        settings.scraping_request_delay_max,
    )
    await asyncio.sleep(base_delay + jitter)


def random_user_agent() -> str:
    """Pick a random User-Agent string."""
    return random.choice(USER_AGENTS)


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int | None = None,
    timeout: float = 30.0,
) -> httpx.Response:
    """
    HTTP GET with exponential backoff and retry on transient errors.
    Raises the last exception after all retries are exhausted.
    """
    settings = get_settings()
    retries = max_retries or settings.scraping_max_retries
    last_error: Exception | None = None

    for attempt in range(retries):
        try:
            await rate_limit_delay()
            resp = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": random_user_agent()},
            )
            # Retry on rate-limit or server unavailable
            if resp.status_code in (429, 503):
                wait = 2 ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Scraper rate-limited / unavailable",
                    extra={"status": resp.status_code, "url": url[:100], "wait": round(wait, 1)},
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            last_error = e
            logger.warning(
                "Scraper fetch failed",
                extra={"attempt": attempt + 1, "url": url[:100], "error": str(e)[:120]},
            )
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 1))

    if last_error:
        raise last_error
    raise RuntimeError("fetch_with_retry exhausted retries")


def build_httpx_client() -> httpx.AsyncClient:
    """Create a shared httpx client with sensible defaults for scraping."""
    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={
            "User-Agent": random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
