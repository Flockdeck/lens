"""There is no API key: the service is for this machine only. What stands in for one is a check, on
every request, that it was addressed to this machine and, for writes, that no other site's page sent
it."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.app import create_app
from session_lens.api.deps import get_store_provider
from session_lens.api.local import normalise_hosts
from session_lens.config import Settings
from session_lens.db.models import BatchItem
from session_lens.storage.memory import InMemoryStore
from tests.api.test_batches import files
from tests.api.test_sessions import seed

READS = ["/sessions", "/sessions/1", "/sessions/1/events", "/batches/1", "/stats/usage", "/config"]
WRITES = [
    ("POST", "/sessions/1/enrich"),
    ("POST", "/batches/1/cancel"),
    ("POST", "/batches/1/retry"),
    ("DELETE", "/sessions/1"),
]


async def test_no_credentials_are_needed(client: httpx.AsyncClient) -> None:
    for path in ("/sessions", "/stats/usage", "/config", "/batches/1/../sessions"):
        assert (await client.get(path)).status_code != 401
    assert "www-authenticate" not in (await client.get("/sessions")).headers


@pytest.mark.parametrize("path", READS + ["/healthz", "/readyz", "/metrics", "/"])
@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8000", "test.evil.example", "testx", "", "127.0.0.1"]
)
async def test_a_request_addressed_to_another_host_is_refused(
    client: httpx.AsyncClient, path: str, host: str
) -> None:
    """DNS rebinding: the page's hostname resolves to this machine but is still what it sends."""
    resp = await client.get(path, headers={"Host": host})
    assert resp.status_code == 421
    assert resp.json() == {"detail": "host not allowed"}
    assert resp.headers["cache-control"] == "no-store"


async def test_the_default_names_are_loopback_and_ipv6_brackets_are_understood() -> None:
    assert Settings().allowed_hosts == ["127.0.0.1", "localhost", "::1"]
    assert normalise_hosts(["[::1]:8000", "LOCALHOST", " 127.0.0.1:80 "]) == {
        "::1",
        "localhost",
        "127.0.0.1",
    }


@pytest.fixture
async def loopback_client(app_settings: Settings, store: InMemoryStore) -> Any:
    """The same app, with the default allowed names and addressed the way a browser addresses it."""
    app = create_app(app_settings.model_copy(update={"allowed_hosts": Settings().allowed_hosts}))
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as c:
            yield c


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "LocalHost"])
async def test_this_machines_own_names_are_accepted(
    loopback_client: httpx.AsyncClient, host: str
) -> None:
    assert (await loopback_client.get("/healthz", headers={"Host": host})).status_code == 200


async def test_a_page_on_another_site_cannot_upload(
    loopback_client: httpx.AsyncClient, db: AsyncSession, make_jsonl: Any
) -> None:
    attempts: list[dict[str, str]] = [
        {"Origin": "http://evil.example"},
        {"Origin": "https://127.0.0.1.evil.example"},
        {"Origin": "http://localhost.evil.example:8000"},
        {"Origin": "null"},  # a sandboxed iframe or a file:// page
        {"Sec-Fetch-Site": "cross-site"},
    ]
    for headers in attempts:
        resp = await loopback_client.post(
            "/batches", files=files(("a.jsonl", make_jsonl(1))), headers=headers
        )
        assert resp.status_code == 403, headers
        assert resp.json() == {"detail": "cross-origin request refused"}
    assert await db.scalar(select(func.count()).select_from(BatchItem)) == 0  # nothing was stored


async def test_the_same_origin_and_plain_scripts_can_upload(
    loopback_client: httpx.AsyncClient, make_jsonl: Any
) -> None:
    for headers in (
        {},  # curl, a script, the test suite: no Origin at all
        {"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin"},
        {"Origin": "http://localhost:8000"},
        {"Origin": "http://[::1]:8000"},
    ):
        resp = await loopback_client.post(
            "/batches", files=files(("a.jsonl", make_jsonl(1))), headers=headers
        )
        assert resp.status_code == 202, (headers, resp.text)


@pytest.mark.parametrize(("method", "path"), WRITES)
async def test_every_write_refuses_a_foreign_origin(
    loopback_client: httpx.AsyncClient, method: str, path: str
) -> None:
    resp = await loopback_client.request(method, path, headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403


async def test_a_foreign_page_cannot_delete_a_session(
    loopback_client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "keep-me", raw=make_jsonl(1))
    resp = await loopback_client.delete(
        f"/sessions/{row.id}", headers={"Origin": "http://evil.example"}
    )
    assert resp.status_code == 403
    assert (await loopback_client.get(f"/sessions/{row.id}")).status_code == 200
    assert (await loopback_client.delete(f"/sessions/{row.id}")).status_code == 204


async def test_responses_never_invite_other_origins_to_read_them(
    loopback_client: httpx.AsyncClient,
) -> None:
    """No CORS headers at all: a browser will not hand a response to a page on another origin."""
    resp = await loopback_client.get("/sessions", headers={"Origin": "http://evil.example"})
    assert not any(k.lower().startswith("access-control-") for k in resp.headers)
    preflight = await loopback_client.options(
        "/batches",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert not any(k.lower().startswith("access-control-") for k in preflight.headers)


async def test_a_refusal_does_not_log_what_the_caller_chose(
    loopback_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await loopback_client.get("/sessions", headers={"Host": "secret-host.evil.example"})
    await loopback_client.post("/batches", headers={"Origin": "http://secret-origin.evil.example"})
    assert "evil.example" not in caplog.text
    assert "request refused" in caplog.text
