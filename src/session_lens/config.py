"""Settings, read from the environment (prefix-free, upper-case)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # mysql+asyncmy://user:password@host:3306/dbname?charset=utf8mb4
    database_url: str = (
        "mysql+asyncmy://session_lens:session_lens@127.0.0.1:3306/session_lens?charset=utf8mb4"
    )

    # Names this machine answers to. A request addressed to any other name (DNS rebinding) is
    # refused, and so is a write from a page on another origin. To change the list, set
    # ALLOWED_HOSTS='["127.0.0.1", "localhost"]'.
    allowed_hosts: list[str] = ["127.0.0.1", "localhost", "::1"]

    # mock (default) and ollama send nothing anywhere. anthropic is the one remote option: it
    # sends the bounded session digest (not the raw recording) to the Anthropic API, if chosen.
    enricher: Literal["mock", "ollama", "anthropic"] = "mock"
    anthropic_api_key: SecretStr | None = None  # ANTHROPIC_API_KEY; never logged or returned
    anthropic_model: str = "claude-haiku-4-5"
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
    # Set the process's termination grace period above it.
    shutdown_grace_seconds: float = 25.0
    # The worker runs retention cleanup in-process this often; 0 disables it.
    cleanup_interval_seconds: int = 3600

    # Where raw recordings are kept. Recordings never leave the machine with the default
    # filesystem store; "s3" is an optional store for a bucket you run yourself.
    storage: Literal["filesystem", "s3"] = "filesystem"
    data_dir: str = "./data"
    # Raw files older than this are deleted by cleanup (0 keeps them forever). Sessions, metrics
    # and enrichments are kept.
    raw_retention_days: int = 30
    # Object key prefix (both stores): keys look like `recordings/YYYY/MM/<uuid>.jsonl`.
    s3_prefix: str = "recordings/"

    # Only used when storage="s3".
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "session-lens"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    # "path" for SeaweedFS/MinIO-style servers; "auto" lets botocore choose (path-style for IP
    # endpoints).
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
    s3_connect_timeout: float = 5.0
    s3_read_timeout: float = 30.0
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
