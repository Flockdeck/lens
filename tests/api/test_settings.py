"""Settings made from the UI: stored in the database, read back without the key, and checked."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lens.api.app import create_app
from lens.api.deps import get_store_provider
from lens.config import Settings
from lens.db.models import AppSetting
from lens.storage.memory import InMemoryStore

SECRET = "sk-ant-test-0123456789abcdef"


async def test_defaults_come_from_the_environment(client: httpx.AsyncClient) -> None:
    body = (await client.get("/settings")).json()
    assert body == {
        "enricher": "mock",
        "anthropic_api_key": {"set": False, "source": None},
        "anthropic_model": "claude-haiku-4-5",
        "anthropic_workspace_id": None,
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "llama3.1:8b",
        "overridden": [],
    }


async def test_the_workspace_id_is_saved_trimmed_and_can_be_removed(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.put("/settings", json={"anthropic_workspace_id": " wrkspc_1 "})).json()
    assert body["anthropic_workspace_id"] == "wrkspc_1"
    assert body["overridden"] == ["anthropic_workspace_id"]
    resp = await client.put("/settings", json={"anthropic_workspace_id": "two words"})
    assert resp.status_code == 422
    body = (await client.put("/settings", json={"anthropic_workspace_id": None})).json()
    assert body["anthropic_workspace_id"] is None


async def test_a_key_is_stored_but_never_returned_or_logged(
    client: httpx.AsyncClient, db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    resp = await client.put(
        "/settings", json={"enricher": "anthropic", "anthropic_api_key": f"  {SECRET}  "}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enricher"] == "anthropic"
    assert resp.json()["anthropic_api_key"] == {"set": True, "source": "settings"}
    assert SECRET not in resp.text
    assert SECRET not in (await client.get("/settings")).text
    assert SECRET not in (await client.get("/config")).text
    assert SECRET not in caplog.text
    stored = {r.key: r.value for r in (await db.execute(select(AppSetting))).scalars()}
    assert stored["anthropic_api_key"] == SECRET  # trimmed
    assert (await client.get("/config")).json()["enricher"] == "anthropic"


async def test_anthropic_needs_a_key(client: httpx.AsyncClient, db: AsyncSession) -> None:
    resp = await client.put("/settings", json={"enricher": "anthropic"})
    assert resp.status_code == 422
    assert "API key" in resp.json()["detail"]
    assert (await db.execute(select(AppSetting))).first() is None  # nothing was saved
    assert (await client.get("/settings")).json()["enricher"] == "mock"


async def test_the_key_cannot_be_removed_while_anthropic_is_chosen(
    client: httpx.AsyncClient,
) -> None:
    await client.put("/settings", json={"enricher": "anthropic", "anthropic_api_key": SECRET})
    resp = await client.put("/settings", json={"anthropic_api_key": None})
    assert resp.status_code == 422
    assert (await client.get("/settings")).json()["anthropic_api_key"]["set"] is True
    # Switching away and removing it in one request is fine.
    resp = await client.put("/settings", json={"enricher": "mock", "anthropic_api_key": None})
    assert resp.status_code == 200
    assert resp.json()["anthropic_api_key"] == {"set": False, "source": None}


async def test_null_puts_the_environment_back(client: httpx.AsyncClient) -> None:
    await client.put("/settings", json={"anthropic_model": "claude-sonnet-5-5"})
    body = (await client.get("/settings")).json()
    assert body["anthropic_model"] == "claude-sonnet-5-5"
    assert body["overridden"] == ["anthropic_model"]
    body = (await client.put("/settings", json={"anthropic_model": None})).json()
    assert body["anthropic_model"] == "claude-haiku-4-5"
    assert body["overridden"] == []


async def test_an_update_leaves_unsent_fields_alone(client: httpx.AsyncClient) -> None:
    await client.put("/settings", json={"ollama_model": "qwen3:8b"})
    await client.put("/settings", json={"anthropic_model": "claude-sonnet-5-5"})
    body = (await client.get("/settings")).json()
    assert (body["ollama_model"], body["anthropic_model"]) == ("qwen3:8b", "claude-sonnet-5-5")


@pytest.mark.parametrize(
    "url", ["http://example.com:11434", "http://10.0.0.5:11434", "ftp://localhost", "not a url"]
)
async def test_an_ollama_url_must_be_this_machine(client: httpx.AsyncClient, url: str) -> None:
    resp = await client.put("/settings", json={"ollama_url": url})
    assert resp.status_code == 422
    assert (await client.get("/settings")).json()["ollama_url"] == "http://127.0.0.1:11434"


async def test_a_local_ollama_url_is_accepted_and_tidied(client: httpx.AsyncClient) -> None:
    resp = await client.put("/settings", json={"ollama_url": "http://localhost:11434/"})
    assert resp.json()["ollama_url"] == "http://localhost:11434"


@pytest.mark.parametrize(
    "body",
    [
        {"enricher": "gpt"},
        {"enricher": ""},
        {"anthropic_model": "   "},
        {"anthropic_api_key": "two words"},
        {"anthropic_api_key": "k" * 600},
        {"api_token": "x"},  # unknown field
    ],
)
async def test_bad_input_is_refused(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    assert (await client.put("/settings", json=body)).status_code == 422


async def test_the_key_from_the_environment_counts(
    app_settings: Settings, store: InMemoryStore
) -> None:
    settings = app_settings.model_copy(update={"anthropic_api_key": SecretStr(SECRET)})
    app = create_app(settings)
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/settings")).json()["anthropic_api_key"] == {
                "set": True,
                "source": "environment",
            }
            resp = await c.put("/settings", json={"enricher": "anthropic"})
            assert resp.status_code == 200
            assert SECRET not in resp.text


async def test_a_page_on_another_site_cannot_change_settings(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.put(
        "/settings",
        json={"enricher": "anthropic", "anthropic_api_key": SECRET},
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403
    assert (await client.get("/settings")).json()["anthropic_api_key"]["set"] is False
    assert not any(
        k.lower().startswith("access-control-") for k in (await client.get("/settings")).headers
    )


async def test_settings_are_never_cached(client: httpx.AsyncClient) -> None:
    assert (await client.get("/settings")).headers["cache-control"] == "no-store"
