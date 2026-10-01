"""Settings, read from the environment (prefix-free, upper-case)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # mysql+asyncmy://user:password@host:3306/dbname?charset=utf8mb4
    database_url: str = "mysql+asyncmy://session_lens:session_lens@127.0.0.1:3306/session_lens?charset=utf8mb4"
    api_token: str = "dev-token"

    enricher: Literal["mock", "anthropic"] = "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5"

    # Upload limits. Flockdeck caps a recording at 16 MiB.
    max_file_bytes: int = 17 * 1024 * 1024
    max_files_per_batch: int = 100
    max_request_bytes: int = 256 * 1024 * 1024

    # Worker.
    worker_concurrency: int = 4
    worker_poll_seconds: float = 1.0
    max_attempts: int = 4
    claim_timeout_seconds: int = 300

    raw_retention_days: int = 30
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
