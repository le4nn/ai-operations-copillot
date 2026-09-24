"""Validated application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for process configuration."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    app_name: str = "AI Operations Copilot"
    app_version: str = "0.6.0"
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", min_length=1, max_length=100)
    openai_timeout_seconds: float = Field(default=20, gt=0, le=120)
    openai_max_retries: int = Field(default=1, ge=0, le=2)
    openai_max_output_tokens: int = Field(default=4096, ge=256, le=16384)
    rag_min_similarity: float = Field(default=0.3, ge=0, le=1)
    chat_deadline_seconds: float = Field(default=45, gt=0, le=180)
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://copilot:copilot_local_only@localhost:5432/copilot"
    )
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_api_key(cls, value: str | SecretStr | None) -> str | None:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        return value.strip() or None if value is not None else None


@lru_cache
def get_settings() -> Settings:
    """Create settings once per process; tests can clear the cache explicitly."""
    return Settings()
