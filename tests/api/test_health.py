import logging

import httpx
import pytest
from pydantic import SecretStr

from session_lens.api.app import create_app
from session_lens.api.deps import get_store_provider
from session_lens.config import Settings
from session_lens.storage.memory import InMemoryStore


async def test_probes_answer(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).status_code == 200
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "session_lens_queue_items" in metrics.text


async def test_request_metrics_recorded(client: httpx.AsyncClient) -> None:
    await client.get("/stats/usage")
    text = (await client.get("/metrics")).text
    assert 'route="/stats/usage"' in text


async def test_static_ui_hides_python_sources(client: httpx.AsyncClient) -> None:
    assert (await client.get("/__init__.py")).status_code == 404


async def test_readyz_503_when_store_down(client: httpx.AsyncClient, store: InMemoryStore) -> None:
    async def down() -> None:
        raise ConnectionError("store down")

    store.ping = down  # type: ignore[method-assign]
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/healthz")).status_code == 200


async def test_readyz_503_when_db_unreachable(database_url: str, store: InMemoryStore) -> None:
    from session_lens.api.app import create_app
    from session_lens.api.deps import get_store_provider
    from session_lens.config import Settings

    bad = (
        "sqlite+aiosqlite:///file:"
        + database_url.rsplit("/", 1)[0].split(":///")[1]
        + "/missing.db?mode=ro&uri=true"
    )
    app = create_app(Settings(database_url=bad, allowed_hosts=["test"]))
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/healthz")).status_code == 200
            assert (await c.get("/readyz")).status_code == 503
            assert (await c.get("/metrics")).status_code == 200


async def test_config_reports_a_remote_enricher_but_never_the_key(
    app_settings: Settings, store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "sk-ant-test-0123456789"
    settings = app_settings.model_copy(
        update={"enricher": "anthropic", "anthropic_api_key": SecretStr(secret)}
    )
    app = create_app(settings)
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    caplog.set_level(logging.DEBUG)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/config")
    assert resp.status_code == 200
    assert resp.json()["enricher"] == "anthropic"
    assert secret not in resp.text
    assert "anthropic_api_key" not in resp.text
    assert secret not in caplog.text


def test_the_tests_do_not_inherit_the_developers_enricher() -> None:
    """`.env` holds the real choice; a test that read it would call the Anthropic API."""
    settings = Settings()
    assert settings.enricher == "mock"
    assert not (settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value())
