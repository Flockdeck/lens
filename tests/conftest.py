"""Shared fixtures: one throwaway SQLite database per test run, built by the real Alembic
migration (so the migration is exercised by every suite that touches the database)."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from session_lens.config import Settings
from session_lens.db.migrate import upgrade

# The tests never read the developer's own choices. Settings reads `.env` (where the real
# ENRICHER and ANTHROPIC_API_KEY live), and a test that built its settings from it would call the
# Anthropic API. Environment variables win over `.env`, so pin the enrichment ones here.
for _name, _value in {
    "ENRICHER": "mock",
    "ANTHROPIC_API_KEY": "",
    "ANTHROPIC_MODEL": "claude-haiku-4-5",
    "OLLAMA_URL": "http://127.0.0.1:11434",
    "OLLAMA_MODEL": "llama3.1:8b",
}.items():
    os.environ[_name] = _value


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A fresh database file for this run, created from the migration and deleted after."""
    folder = Path(tempfile.mkdtemp(prefix="session-lens-test-"))
    url = f"sqlite+aiosqlite:///{(folder / 'test.db').as_posix()}"
    try:
        upgrade(Settings(database_url=url))
        yield url
    finally:
        shutil.rmtree(folder, ignore_errors=True)
