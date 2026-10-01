"""Local-only privacy properties: no caching, no query strings or filenames in logs, no CORS."""

import logging
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.app import warn_if_not_loopback
from session_lens.api.logging import JsonFormatter
from session_lens.config import Settings
from session_lens.storage.memory import InMemoryStore
from tests.api.test_batches import files
from tests.api.test_sessions import seed

NO_STORE_PATHS = [
    "/sessions",
    "/sessions/1",
    "/sessions/1/events",
    "/batches/1",
    "/stats/trends",
    "/stats/compare",
    "/stats/usage",
    "/config",
]


async def test_no_store_on_sensitive_responses(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    await seed(db, store, "s1", raw=make_jsonl(1))
    for path in NO_STORE_PATHS:  # includes 404s and 4xx: error bodies must not be cached either
        resp = await client.get(path)
        assert resp.headers["cache-control"] == "no-store", path
    unauthorised = await client.get("/sessions", headers={"Authorization": ""})
    assert unauthorised.status_code == 401
    assert unauthorised.headers["cache-control"] == "no-store"
    posted = await client.post("/batches", files=files(("a.jsonl", make_jsonl(1))))
    assert posted.headers["cache-control"] == "no-store"


async def test_probes_and_ui_are_not_marked_no_store(client: httpx.AsyncClient) -> None:
    assert "cache-control" not in (await client.get("/healthz")).headers


async def test_logs_never_contain_query_strings_or_filenames(
    client: httpx.AsyncClient,
    db: AsyncSession,
    store: InMemoryStore,
    make_jsonl: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed(db, store, "s1", project="hush-project")
    with caplog.at_level(logging.DEBUG):
        await client.get("/sessions", params={"project": "hush-project", "agent": "hush-agent"})
        await client.post(
            "/batches",
            files=files(
                ("hush-name.jsonl", make_jsonl(1)),
                ("hush-rejected.txt", b"x"),
            ),
        )
        await client.post("/batches", files=files(("hush-all-rejected.txt", b"x")))
    formatter = JsonFormatter()
    lines = [formatter.format(r) for r in caplog.records if r.name.startswith("session_lens")]
    assert any('"msg": "request"' in line for line in lines)
    for line in lines:
        assert "hush" not in line, line
        assert "?" not in line, line


async def test_cors_is_closed(client: httpx.AsyncClient) -> None:
    resp = await client.options(
        "/sessions",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert not [h for h in resp.headers if h.lower().startswith("access-control-")]
    simple = await client.get("/sessions", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_non_loopback_bind_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert warn_if_not_loopback("0.0.0.0") is True
        assert warn_if_not_loopback("192.168.1.5") is True
        assert warn_if_not_loopback("example.internal") is True
    assert len(caplog.records) == 3
    caplog.clear()
    for host in ("127.0.0.1", "::1", "localhost"):
        assert warn_if_not_loopback(host) is False
    assert not caplog.records


async def test_config_endpoint(client: httpx.AsyncClient, app_settings: Settings) -> None:
    resp = await client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "storage",
        "enricher",
        "raw_retention_days",
        "cleanup_interval_seconds",
        "version",
    }
    assert body["storage"] in {"filesystem", "s3"}
    assert body["enricher"] == app_settings.enricher
    assert body["raw_retention_days"] == app_settings.raw_retention_days
    assert body["cleanup_interval_seconds"] is None or body["cleanup_interval_seconds"] > 0
    assert isinstance(body["version"], str) and body["version"]
    for secret in (app_settings.api_token, "mysql", "password", "secret", "api_key"):
        assert secret not in resp.text.lower()


async def test_config_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/config", headers={"Authorization": ""})).status_code == 401
    assert (
        await client.get("/config", headers={"Authorization": "Bearer nope"})
    ).status_code == 401
