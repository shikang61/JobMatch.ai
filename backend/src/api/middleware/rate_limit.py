"""
Rate limiting using in-memory sliding window for MVP. Replace with Redis for multi-instance.
Auth: configurable attempts per window per IP. API: configurable requests per minute per user.
"""
import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, status

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Maximum number of distinct keys before we evict old entries.
# Prevents unbounded memory growth from many unique IPs.
_MAX_KEYS = 10_000

# In-memory: key -> list of timestamps (for sliding window)
_auth_timestamps: dict[str, list[float]] = defaultdict(list)
_api_timestamps: dict[str, list[float]] = defaultdict(list)


def _get_client_id(request: Request, use_user_id: bool = False) -> str:
    """Identify client: user id if authenticated, else IP."""
    if use_user_id:
        uid = getattr(request.state, "user_id", None)
        if uid:
            return f"user:{uid}"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_old(timestamps: list[float], window_seconds: float) -> None:
    """Remove timestamps older than the window."""
    cutoff = time.monotonic() - window_seconds
    while timestamps and timestamps[0] < cutoff:
        timestamps.pop(0)


def _evict_stale_keys(store: dict[str, list[float]], window_seconds: float) -> None:
    """Remove keys with no recent timestamps to cap memory usage."""
    if len(store) <= _MAX_KEYS:
        return
    cutoff = time.monotonic() - window_seconds
    stale = [k for k, ts in store.items() if not ts or ts[-1] < cutoff]
    for k in stale:
        del store[k]


def check_auth_rate_limit(request: Request) -> None:
    """Enforce auth rate limit per client IP. Call before login/register."""
    settings = get_settings()
    key = _get_client_id(request, use_user_id=False)
    window = settings.rate_limit_auth_window_minutes * 60
    now = time.monotonic()
    _prune_old(_auth_timestamps[key], window)
    if len(_auth_timestamps[key]) >= settings.rate_limit_auth_requests:
        logger.warning("Auth rate limit exceeded", extra={"client": key[:20]})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )
    _auth_timestamps[key].append(now)
    _evict_stale_keys(_auth_timestamps, window)


def check_api_rate_limit(request: Request, user_id: str | None) -> None:
    """Enforce API rate limit per user (or per IP if unauthenticated)."""
    settings = get_settings()
    key = f"user:{user_id}" if user_id else _get_client_id(request, use_user_id=False)
    window = float(settings.rate_limit_api_window_seconds)
    now = time.monotonic()
    _prune_old(_api_timestamps[key], window)
    if len(_api_timestamps[key]) >= settings.rate_limit_api_requests:
        logger.warning("API rate limit exceeded", extra={"key": key[:30]})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )
    _api_timestamps[key].append(now)
    _evict_stale_keys(_api_timestamps, window)


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Global middleware stub. Per-route rate limiting is used instead via check_* helpers."""
    if request.url.path in ("/health", "/docs", "/redoc", "/openapi.json"):
        return await call_next(request)
    response = await call_next(request)
    return response
