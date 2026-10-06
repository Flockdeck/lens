"""Settings, read from the environment (prefix-free, upper-case)."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from platformdirs import user_data_dir
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Left blank, the database is a SQLite file in `data_dir`. Set it to point somewhere else, e.g.
    # sqlite+aiosqlite:///C:/path/to/lens.db
    database_url: str = ""

    # Names this machine answers to. A request addressed to any other name (DNS rebinding) is
    # refused, and so is a write from a page on another origin. To change the list, set
    # ALLOWED_HOSTS to one name, to names separated by commas or spaces, or to a JSON list:
    # 127.0.0.1 | 127.0.0.1,localhost | ["127.0.0.1", "localhost"]. (A program that starts lens,
    # Flockdeck for one, passes it as a plain name, which pydantic would otherwise reject.)
    allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "localhost", "::1"]

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _read_allowed_hosts(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None  # "[::1]" is an IPv6 name, not a list
            if isinstance(parsed, list):
                return parsed
        return [name for name in re.split(r"[,\s]+", text) if name]

    # mock (default) and ollama send nothing anywhere. anthropic is the one remote option: it
    # sends the bounded session digest (not the raw recording) to the Anthropic API, if chosen.
    enricher: Literal["mock", "ollama", "anthropic"] = "mock"
    anthropic_api_key: SecretStr | None = None  # ANTHROPIC_API_KEY; never logged or returned
    anthropic_model: str = "claude-haiku-4-5"
    # ANTHROPIC_WORKSPACE_ID: only for a key that is not scoped to one workspace.
    anthropic_workspace_id: str | None = None
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

    # Everything lens keeps lives here: the SQLite database and the raw recordings. The
    # default is the per-user data directory of the operating system.
    data_dir: str = Field(default_factory=lambda: user_data_dir("lens", appauthor=False))
    # Raw files older than this are deleted by cleanup (0 keeps them forever). Sessions, metrics
    # and enrichments are kept.
    raw_retention_days: int = 30
    # Subdirectory of `data_dir` for the raw recordings: `recordings/YYYY/MM/<uuid>.jsonl`.
    store_prefix: str = "recordings/"

    log_level: str = "INFO"
    # "-": standard output. Blank: standard output in a terminal, else a file in data_dir.
    log_file: str = ""

    # Where `lens serve` listens. Loopback only: there is no API key.
    host: str = "127.0.0.1"
    port: int = 8000

    @model_validator(mode="after")
    def _default_database(self) -> Self:
        if not self.database_url.strip():
            path = Path(self.data_dir).expanduser() / "lens.db"
            self.database_url = f"sqlite+aiosqlite:///{path.as_posix()}"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
