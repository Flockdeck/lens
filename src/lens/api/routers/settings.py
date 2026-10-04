"""Settings made from the UI: which enricher, and its keys and models.

The Anthropic key is write-only: it can be set or removed, and the API only ever says whether one is
in effect and where it came from. Changes are stored in the database, so the worker picks them up
within a couple of seconds without a restart. `null` for a field removes the override, which puts
back the value from the environment.
"""

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lens.api.deps import get_app_settings
from lens.config import Settings
from lens.enrich.ollama import require_local_url
from lens.runtime_settings import (
    apply_overrides,
    key_source,
    load_overrides,
    save_overrides,
)

router = APIRouter(tags=["settings"])
log = logging.getLogger("lens.api.settings")

MAX_KEY_CHARS = 512
MAX_NAME_CHARS = 128


class KeyState(BaseModel):
    set: bool
    source: Literal["settings", "environment"] | None


class SettingsView(BaseModel):
    enricher: Literal["mock", "ollama", "anthropic"]
    anthropic_api_key: KeyState
    anthropic_model: str
    ollama_url: str
    ollama_model: str
    # Names of the settings changed here (the rest come from the environment).
    overridden: list[str]


class SettingsUpdate(BaseModel):
    """Send only what changes. `null` removes the override."""

    model_config = ConfigDict(extra="forbid")

    enricher: Literal["mock", "ollama", "anthropic"] | None = None
    anthropic_api_key: str | None = Field(default=None, max_length=MAX_KEY_CHARS)
    anthropic_model: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    ollama_url: str | None = Field(default=None, max_length=MAX_NAME_CHARS * 2)
    ollama_model: str | None = Field(default=None, max_length=MAX_NAME_CHARS)


def _sm(request: Request) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    return sm


def _view(base: Settings, overrides: dict[str, str]) -> SettingsView:
    effective = apply_overrides(base, overrides)
    source = key_source(base, overrides)
    return SettingsView(
        enricher=effective.enricher,
        anthropic_api_key=KeyState(set=source is not None, source=source),
        anthropic_model=effective.anthropic_model,
        ollama_url=effective.ollama_url,
        ollama_model=effective.ollama_model,
        overridden=sorted(overrides),
    )


@router.get("/settings", response_model=SettingsView)
async def get_settings_view(
    request: Request, base: Annotated[Settings, Depends(get_app_settings)]
) -> SettingsView:
    return _view(base, await load_overrides(_sm(request)))


@router.put("/settings", response_model=SettingsView)
async def update_settings(
    request: Request,
    body: SettingsUpdate,
    base: Annotated[Settings, Depends(get_app_settings)],
) -> SettingsView:
    sm = _sm(request)
    sent = body.model_fields_set
    changes: dict[str, str | None] = {}
    for name in sent:
        value: Any = getattr(body, name)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise HTTPException(422, f"{name} is empty")
        changes[name] = value

    key = changes.get("anthropic_api_key")
    if key is not None and any(c.isspace() for c in key):
        raise HTTPException(422, "the API key has whitespace in it")
    url = changes.get("ollama_url")
    if url is not None:
        try:
            changes["ollama_url"] = require_local_url(url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    overrides = await load_overrides(sm)
    after = {k: v for k, v in overrides.items() if k not in changes}
    after.update({k: v for k, v in changes.items() if v is not None})
    if apply_overrides(base, after).enricher == "anthropic" and key_source(base, after) is None:
        raise HTTPException(422, "the anthropic enricher needs an API key")

    await save_overrides(sm, changes)
    # Names only: never the key, and nothing a caller chose.
    log.info("settings changed", extra={"changed": sorted(changes)})
    return _view(base, after)
