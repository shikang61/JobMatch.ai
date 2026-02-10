"""
Base OpenAI client with timeout, retries, and token awareness.
"""
import json
from typing import Any

from openai import AsyncOpenAI
from openai import APIError, APITimeoutError

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMServiceError(Exception):
    """Raised when LLM API fails after retries."""

    pass


def get_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMServiceError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def chat_completion_json(
    client: AsyncOpenAI,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """
    Call OpenAI chat with JSON response. Retries with exponential backoff.
    Returns parsed JSON dict. Raises LLMServiceError on failure.
    """
    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(settings.openai_max_retries):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                timeout=float(settings.openai_timeout_seconds),
            )
            choice = response.choices[0]
            if not choice.message.content:
                raise LLMServiceError("Empty response from model")
            return json.loads(choice.message.content)
        except (APIError, APITimeoutError) as e:
            last_error = e
            logger.warning(
                "OpenAI API attempt failed",
                extra={"attempt": attempt + 1, "error": str(e)[:200]},
            )
            if attempt < settings.openai_max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)
    raise LLMServiceError(f"OpenAI API failed after retries: {last_error}")
