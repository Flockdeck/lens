"""Settings changed from the UI. They are stored in the database, so the API and the worker (two
processes) see the same values, and they override the environment. Deleting an override puts the
environment's value back.

Only enrichment is editable: which enricher, the Anthropic key and model, the Ollama URL and model.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lens.config import Settings
from lens.db.models import AppSetting
from lens.enrich.base import Enricher, EnrichmentError, EnrichmentResult, build_enricher
from lens.recording.models import Analysis

log = logging.getLogger(__name__)

EDITABLE = ("enricher", "anthropic_api_key", "anthropic_model", "ollama_url", "ollama_model")
ENRICHERS = ("mock", "ollama", "anthropic")


async def load_overrides(sm: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with sm() as db:
        rows = (await db.execute(select(AppSetting))).scalars().all()
    return {r.key: r.value for r in rows if r.key in EDITABLE}


async def save_overrides(
    sm: async_sessionmaker[AsyncSession], changes: dict[str, str | None]
) -> None:
    """Set each key to its value, or remove the override when the value is None."""
    async with sm() as db, db.begin():
        for key, value in changes.items():
            if key not in EDITABLE:
                raise ValueError(f"not an editable setting: {key}")
            if value is None:
                await db.execute(delete(AppSetting).where(AppSetting.key == key))
                continue
            row = await db.get(AppSetting, key)
            if row is None:
                db.add(AppSetting(key=key, value=value))
            else:
                row.value = value


def apply_overrides(base: Settings, overrides: dict[str, str]) -> Settings:
    update: dict[str, Any] = {k: v for k, v in overrides.items() if k in EDITABLE}
    if "anthropic_api_key" in update:
        update["anthropic_api_key"] = SecretStr(update["anthropic_api_key"])
    if update.get("enricher") not in (None, *ENRICHERS):
        del update["enricher"]
    return base.model_copy(update=update)


async def effective_settings(sm: async_sessionmaker[AsyncSession], base: Settings) -> Settings:
    return apply_overrides(base, await load_overrides(sm))


def key_source(base: Settings, overrides: dict[str, str]) -> str | None:
    """Where the Anthropic key in effect comes from, or None if there is none."""
    if overrides.get("anthropic_api_key", "").strip():
        return "settings"
    if base.anthropic_api_key and base.anthropic_api_key.get_secret_value().strip():
        return "environment"
    return None


def _fingerprint(s: Settings) -> tuple[Any, ...]:
    key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else ""
    if s.enricher == "anthropic":
        return ("anthropic", key, s.anthropic_model)
    if s.enricher == "ollama":
        return ("ollama", s.ollama_url, s.ollama_model, s.ollama_timeout_seconds)
    return ("mock",)


class DynamicEnricher:
    """An `Enricher` that follows the settings: before each call it looks at the stored overrides
    (at most every `ttl` seconds), and builds a new enricher when they changed. A bad setting fails
    the item that hit it, permanently, with a message that names the setting; fixing the setting and
    retrying the item works without restarting anything."""

    def __init__(
        self, sm: async_sessionmaker[AsyncSession], base: Settings, *, ttl: float = 2.0
    ) -> None:
        self._sm = sm
        self._base = base
        self._ttl = ttl
        self._checked = float("-inf")
        self._fingerprint: tuple[Any, ...] | None = None
        self._inner: Enricher | None = None
        self._error: str | None = None
        self._lock = asyncio.Lock()

    async def _current(self) -> Enricher:
        async with self._lock:
            if self._fingerprint is None or time.monotonic() - self._checked >= self._ttl:
                settings = await effective_settings(self._sm, self._base)
                self._checked = time.monotonic()
                fingerprint = _fingerprint(settings)
                if fingerprint != self._fingerprint:
                    self._fingerprint = fingerprint
                    self._inner, self._error = None, None
                    try:
                        # Building a client loads the TLS certificates, which takes seconds on
                        # some machines (and longer in a freshly unpacked binary); on the event
                        # loop that would freeze the web UI.
                        self._inner = await asyncio.to_thread(build_enricher, settings)
                    except ValueError as exc:  # a missing key, a URL that is not local
                        self._error = str(exc)
                        log.warning("enricher not usable", extra={"enricher": settings.enricher})
            inner, error = self._inner, self._error
        if inner is None:
            raise EnrichmentError(f"enricher is not configured: {error}", retryable=False)
        return inner

    async def enrich(self, analysis: Analysis) -> EnrichmentResult:
        return await (await self._current()).enrich(analysis)


__all__ = [
    "EDITABLE",
    "ENRICHERS",
    "DynamicEnricher",
    "Enricher",
    "apply_overrides",
    "effective_settings",
    "key_source",
    "load_overrides",
    "save_overrides",
]
