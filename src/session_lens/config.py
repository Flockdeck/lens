"""Settings, read from the environment (prefix-free, upper-case)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # mysql+asyncmy://user:password@host:3306/dbname?charset=utf8mb4
    database_url: str = (
        "mysql+asyncmy://session_lens:session_lens@127.0.0.1:3306/session_lens?charset=utf8mb4"
    )
    api_token: str = "dev-token"

    enricher: Literal["mock", "ollama"] = "mock"
    # Local only: the URL must be this machine (checked when the enricher is built).
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: float = 120.0

    # Upload limits. Flockdeck caps a recording at 16 MiB.
    max_file_bytes: int = 17 * 1024 * 1024
    max_files_per_batch: int = 100
    max_request_bytes: int = 256 * 1024 * 1024

    # Worker.
    worker_concurrency: int = 4
    worker_poll_seconds: float = 1.0
    max_attempts: int = 4
    claim_timeout_seconds: int = 300
    # On SIGTERM the worker waits this long for in-flight items, then cancels and re-queues them.
    # Set the pod's terminationGracePeriodSeconds above it.
    shutdown_grace_seconds: float = 25.0

    # Raw recordings live in an S3-compatible bucket (DigitalOcean Spaces in the cluster, SeaweedFS
    # locally and in CI). The bucket's lifecycle rule must expire objects after
    # `raw_retention_days`; the app marks rows expired on the same schedule.
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "session-lens"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_prefix: str = "recordings/"
    # Spaces works with "virtual"; SeaweedFS (local compose) needs "path". "auto" lets botocore
    # choose (path-style for IP-address endpoints).
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
    s3_connect_timeout: float = 5.0
    s3_read_timeout: float = 30.0
    raw_retention_days: int = 30
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
