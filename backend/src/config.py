"""
Application configuration loaded from environment variables.
All sensitive and environment-specific values live here.
"""
import json
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/jobmatch",
        description="PostgreSQL connection URL (asyncpg driver for async)",
    )
    database_url_sync: Optional[str] = Field(
        default=None,
        description="Sync URL for migrations (postgresql:// without asyncpg)",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")

    # JWT
    jwt_secret: str = Field(
        default="change-me-in-production-use-at-least-32-chars-secret",
        min_length=32,
        description="Secret for signing JWTs",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)

    # Rate limiting
    rate_limit_auth_requests: int = Field(default=50, ge=1, description="Auth attempts per window")
    rate_limit_auth_window_minutes: int = Field(default=15, ge=1)
    rate_limit_api_requests: int = Field(default=100, ge=10)
    rate_limit_api_window_seconds: int = Field(default=60, ge=1)

    # File upload
    cv_max_size_mb: int = Field(default=5, ge=1, le=10)
    cv_allowed_content_types: tuple = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4-turbo-preview")
    openai_timeout_seconds: int = Field(default=30, ge=5)
    openai_max_retries: int = Field(default=3, ge=1)

    # LLM cache (Redis)
    llm_cache_ttl_days: int = Field(default=7, ge=1)

    # Scraping
    scraping_enabled: bool = Field(default=True)
    scraping_rate_limit_per_second: float = Field(default=1.0, ge=0.5)
    scraping_request_delay_min: float = Field(default=1.0, ge=0)
    scraping_request_delay_max: float = Field(default=3.0, ge=0)
    scraping_max_retries: int = Field(default=3, ge=1)

    # App
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins (JSON array string in env)",
    )
    api_prefix: str = Field(default="/api")

    # Matching
    match_min_compatibility: float = Field(default=60.0, ge=0, le=100)
    match_top_n: int = Field(default=20, ge=1, le=100)

    # ElevenLabs (Phase 2)
    elevenlabs_api_key: Optional[str] = Field(default=None)
    elevenlabs_voice_id: Optional[str] = Field(default=None)

    @property
    def cv_max_size_bytes(self) -> int:
        return self.cv_max_size_mb * 1024 * 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v.strip() for v in v.split(",") if v.strip()]
        return ["http://localhost:3000"]

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        u = (v or "INFO").upper()
        if u not in allowed:
            return "INFO"
        return u


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
