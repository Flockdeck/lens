"""The enricher follows the settings made in the UI, without a restart."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from session_lens.config import Settings
from session_lens.enrich.base import EnrichmentError
from session_lens.recording.models import Analysis
from session_lens.runtime_settings import DynamicEnricher, save_overrides
from tests.dbutil import clear_tables, test_engine


@pytest_asyncio.fixture
async def sm(database_url: str) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    engine: AsyncEngine = test_engine(database_url)
    await clear_tables(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_it_starts_on_the_mock(
    sm: async_sessionmaker,
    make_analysis: Callable[..., Analysis],  # type: ignore[type-arg]
) -> None:
    result = await DynamicEnricher(sm, Settings(), ttl=0).enrich(make_analysis())
    assert result.model == "mock"


async def test_a_change_applies_to_the_next_item(
    sm: async_sessionmaker,
    make_analysis: Callable[..., Analysis],  # type: ignore[type-arg]
) -> None:
    enricher = DynamicEnricher(sm, Settings(), ttl=0)
    assert (await enricher.enrich(make_analysis())).model == "mock"

    await save_overrides(sm, {"enricher": "anthropic"})  # no key anywhere
    with pytest.raises(EnrichmentError) as err:
        await enricher.enrich(make_analysis())
    assert err.value.retryable is False
    assert "ANTHROPIC_API_KEY" in str(err.value)

    await save_overrides(sm, {"enricher": None})  # back to the environment's choice
    assert (await enricher.enrich(make_analysis())).model == "mock"


async def test_a_key_set_later_fixes_it_without_a_restart(
    sm: async_sessionmaker,
    make_analysis: Callable[..., Analysis],  # type: ignore[type-arg]
) -> None:
    enricher = DynamicEnricher(sm, Settings(), ttl=0)
    await save_overrides(sm, {"enricher": "anthropic"})
    with pytest.raises(EnrichmentError):
        await enricher.enrich(make_analysis())
    await save_overrides(sm, {"anthropic_api_key": "sk-ant-test-123"})
    inner = await enricher._current()
    assert type(inner).__name__ == "AnthropicEnricher"


async def test_a_non_local_ollama_url_in_the_database_is_still_refused(
    sm: async_sessionmaker,
    make_analysis: Callable[..., Analysis],  # type: ignore[type-arg]
) -> None:
    await save_overrides(sm, {"enricher": "ollama", "ollama_url": "http://example.com:11434"})
    with pytest.raises(EnrichmentError) as err:
        await DynamicEnricher(sm, Settings(), ttl=0).enrich(make_analysis())
    assert err.value.retryable is False
    assert "this machine" in str(err.value)


async def test_the_settings_are_read_at_most_every_ttl(
    sm: async_sessionmaker,
    make_analysis: Callable[..., Analysis],  # type: ignore[type-arg]
) -> None:
    enricher = DynamicEnricher(sm, Settings(), ttl=3600)
    await enricher.enrich(make_analysis())
    await save_overrides(sm, {"enricher": "ollama", "ollama_url": "http://example.com"})
    assert (await enricher.enrich(make_analysis())).model == "mock"  # not looked at again yet
