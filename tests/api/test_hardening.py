"""Auth edge cases, startup safety, upload limits, date filters, failure mapping, logging."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.app import create_app
from session_lens.api.deps import (
    get_enricher_provider,
    get_queue,
    get_store_provider,
)
from session_lens.api.logging import JsonFormatter
from session_lens.config import Settings
from session_lens.db.models import Enrichment
from session_lens.db.models import Session as SessionRow
from tests.api.standins import FakeQueue, InMemoryStore
from tests.api.test_batches import files
from tests.api.test_sessions import _Enricher, names, seed, use_enricher

# ------------------------------------------------------------------ auth and startup


async def test_same_length_wrong_token(client: httpx.AsyncClient) -> None:
    resp = await client.get("/stats/usage", headers={"Authorization": "Bearer test-tokeX"})
    assert resp.status_code == 401


async def test_refuses_default_or_empty_token(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALLOW_INSECURE_DEV", raising=False)
    with pytest.raises(RuntimeError, match="API_TOKEN"):
        create_app(app_settings.model_copy(update={"api_token": "dev-token"}))
    with pytest.raises(RuntimeError, match="API_TOKEN"):
        create_app(app_settings.model_copy(update={"api_token": ""}))


async def test_dev_mode_allows_default_token_and_docs(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "1")
    app = create_app(app_settings.model_copy(update={"api_token": "dev-token"}))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/docs")).status_code == 200
            assert (await c.get("/openapi.json")).status_code == 200


async def test_docs_hidden_outside_dev_mode(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert (await client.get(path)).status_code == 404


# ------------------------------------------------------------------ uploads


async def test_long_filename_rejected(client: httpx.AsyncClient, make_jsonl: Any) -> None:
    long_name = "a" * 300 + ".jsonl"
    resp = await client.post("/batches", files=files((long_name, make_jsonl(1))))
    assert resp.status_code == 422
    assert resp.json()["rejected"][0]["reason"] == "filename too long"


async def test_non_utf8_filename_is_not_a_server_error(
    client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="files"; filename="\xff\xfe.jsonl"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b'{"seq": 1}\n\r\n--b--\r\n'
    )
    resp = await client.post(
        "/batches", content=body, headers={"Content-Type": "multipart/form-data; boundary=b"}
    )
    assert resp.status_code < 500
    if resp.status_code == 202:  # decoded leniently: stored under a sanitised name
        assert len(resp.json()["accepted"]) == 1


async def test_chunked_upload_over_cap_is_413(
    client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    async def body() -> AsyncIterator[bytes]:
        yield (
            b"--b\r\n"
            b'Content-Disposition: form-data; name="files"; filename="a.jsonl"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
        )
        for _ in range(5):  # no Content-Length: 5 x 4000 bytes against the 8192-byte cap
            yield b"x" * 4000

    resp = await client.post(
        "/batches",
        content=body(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert resp.status_code == 413
    assert store.objects == {}


async def test_store_put_failure_is_503(
    client: httpx.AsyncClient, store: InMemoryStore, make_jsonl: Any
) -> None:
    async def boom(key: str, data: bytes) -> None:
        raise ConnectionError("s3 down")

    store.put = boom  # type: ignore[method-assign]
    resp = await client.post("/batches", files=files(("a.jsonl", make_jsonl(1))))
    assert resp.status_code == 503


# ------------------------------------------------------------------ events


async def test_after_seq_past_end(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "s1", raw=make_jsonl(1, 2, 3))
    page = (await client.get(f"/sessions/{row.id}/events", params={"after_seq": 99})).json()
    assert page == {"items": [], "next_after_seq": None}


async def test_events_store_outage_is_503(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "s1", raw=make_jsonl(1))

    async def boom(key: str) -> bytes:
        raise ConnectionError("s3 down")

    store.get = boom  # type: ignore[method-assign]
    assert (await client.get(f"/sessions/{row.id}/events")).status_code == 503
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 503
    # An outage must not mark the recording expired.
    assert (await client.get(f"/sessions/{row.id}")).json()["raw_available"] is True


async def test_store_build_failure_does_not_mask_404(client: httpx.AsyncClient) -> None:
    def broken() -> InMemoryStore:
        raise RuntimeError("bad storage config")

    client.app.dependency_overrides[get_store_provider] = lambda: broken  # type: ignore[attr-defined]
    assert (await client.get("/sessions/9999/events")).status_code == 404
    assert (await client.get("/readyz")).status_code == 503


# ------------------------------------------------------------------ readiness


async def test_readyz_times_out_on_hung_store(
    client: httpx.AsyncClient, store: InMemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from session_lens.api.routers import health

    monkeypatch.setattr(health, "READY_TIMEOUT_SECONDS", 0.05)

    async def hang() -> None:
        await asyncio.sleep(5)

    store.ping = hang  # type: ignore[method-assign]
    resp = await client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["check"] == "store"


# ------------------------------------------------------------------ re-enrich failures


async def test_enricher_build_failure_is_503_but_404_wins(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    def broken() -> _Enricher:
        raise RuntimeError("missing ANTHROPIC_API_KEY")

    client.app.dependency_overrides[get_enricher_provider] = lambda: broken  # type: ignore[attr-defined]
    assert (await client.post("/sessions/9999/enrich")).status_code == 404
    gone = await seed(db, store, "s0")
    assert (await client.post(f"/sessions/{gone.id}/enrich")).status_code == 410
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 503


async def test_enricher_crash_is_502(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    use_enricher(client, _Enricher(ValueError("contains recording text")))
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    resp = await client.post(f"/sessions/{row.id}/enrich")
    assert resp.status_code == 502
    assert "recording text" not in resp.text


class _FlakyQueue(FakeQueue):
    """upsert_enrichment fails with a unique-constraint error `failures` times."""

    def __init__(self, failures: int, delete_session: bool = False) -> None:
        self.failures = failures
        self.delete_session = delete_session
        self.calls = 0

    async def upsert_enrichment(self, session: AsyncSession, session_id: int, result: Any) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            if self.delete_session:
                await session.execute(delete(SessionRow).where(SessionRow.id == session_id))
                await session.commit()
            raise IntegrityError("insert", None, Exception("duplicate"))
        await super().upsert_enrichment(session, session_id, result)


async def test_reenrich_retries_once_on_conflict(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    flaky = _FlakyQueue(failures=1)
    client.app.dependency_overrides[get_queue] = lambda: flaky  # type: ignore[attr-defined]
    use_enricher(client, _Enricher())
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    resp = await client.post(f"/sessions/{row.id}/enrich")
    assert resp.status_code == 200 and flaky.calls == 2
    assert resp.json()["enrichment"]["summary"] == "new summary"


async def test_reenrich_persistent_conflict_is_409(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    client.app.dependency_overrides[get_queue] = lambda: _FlakyQueue(failures=9)  # type: ignore[attr-defined]
    use_enricher(client, _Enricher())
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 409


async def test_reenrich_session_deleted_midway_is_404(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    client.app.dependency_overrides[get_queue] = lambda: _FlakyQueue(1, delete_session=True)  # type: ignore[attr-defined]
    use_enricher(client, _Enricher())
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 404


# ------------------------------------------------------------------ date filters


async def test_session_date_filters(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    await seed(db, store, "noon", started=datetime(2026, 1, 5, 12))
    await seed(db, store, "unstarted", started=None)

    async def q(**params: str) -> list[str]:
        resp = await client.get("/sessions", params=params)
        assert resp.status_code == 200, resp.text
        return sorted(names(resp))

    assert await q() == ["noon", "unstarted"]  # NULL started_at: kept without a range...
    assert await q(to="2026-01-05") == ["noon"]  # ...dropped with one; bare `to` = whole day
    assert await q(to="2026-01-04") == []
    assert await q(**{"from": "2026-01-05"}) == ["noon"]  # bare `from` = 00:00 UTC
    assert await q(**{"from": "2026-01-06"}) == []
    assert await q(**{"from": "2026-01-05", "to": "2026-01-05"}) == ["noon"]
    assert await q(to="2026-01-05T11:59:59Z") == []  # datetime bounds are exact
    assert await q(to="2026-01-05T12:00:00Z") == ["noon"]
    assert await q(**{"from": "2026-01-05T13:00:00+01:00"}) == ["noon"]  # offsets honoured
    assert await q(**{"from": "2026-01-05T12:00:01"}) == []  # naive = UTC
    bad = await client.get("/sessions", params={"from": "yesterday"})
    assert bad.status_code == 422


# ------------------------------------------------------------------ stats


async def test_trends_range_project_and_week(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    await seed(db, store, "a", project="p", started=datetime(2026, 1, 5, 23, 30))
    await seed(db, store, "b", project="p", started=datetime(2026, 1, 12, 0, 30))
    await seed(db, store, "c", project="q", started=datetime(2026, 1, 13))

    def buckets(resp: httpx.Response) -> list[str]:
        assert resp.status_code == 200, resp.text
        return [b["bucket"] for b in resp.json()]

    week = {"interval": "week"}
    assert buckets(await client.get("/stats/trends", params=week)) == ["2026-01-05", "2026-01-12"]
    only_p = {"interval": "week", "project": "p", "to": "2026-01-05"}
    assert buckets(await client.get("/stats/trends", params=only_p)) == ["2026-01-05"]
    later = {"interval": "day", "from": "2026-01-12"}
    assert buckets(await client.get("/stats/trends", params=later)) == ["2026-01-12", "2026-01-13"]
    assert (await client.get("/stats/trends", params={"to": "nope"})).status_code == 422

    compare = (await client.get("/stats/compare", params={"project": "p"})).json()
    assert [(c["key"], c["sessions"]) for c in compare] == [("claude", 2)]


async def test_metrics_json_missing_keys(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    started = datetime(2026, 1, 5)
    await seed(db, store, "no-errors-key", agent="a1", started=started, metrics={"tool_calls": 5})
    await seed(db, store, "no-calls", agent="a2", started=started, metrics={"duration_seconds": 1})
    await seed(db, store, "empty", agent="a3", started=started, metrics={})

    rows = {c["key"]: c for c in (await client.get("/stats/compare")).json()}
    assert rows["a1"]["tool_error_rate"] == 0.0  # calls known, errors absent -> 0
    assert rows["a2"]["tool_error_rate"] is None  # no calls at all
    assert rows["a3"]["permission_denial_rate"] is None
    trend = (await client.get("/stats/trends")).json()
    assert trend[0]["sessions"] == 3 and trend[0]["tool_error_rate"] == 0.0

    listing = (await client.get("/sessions")).json()["items"]
    assert {i["recording_session"]: i["tool_calls"] for i in listing}["empty"] is None


# ------------------------------------------------------------------ unhandled errors


async def test_unhandled_exception_logs_type_and_frames_not_message(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "SECRET recording content"

    def explode() -> None:
        raise RuntimeError(secret)

    client.app.dependency_overrides[get_queue] = explode  # type: ignore[attr-defined]
    with caplog.at_level(logging.INFO):
        resp = await client.post("/batches/1/cancel")
    assert resp.status_code == 500
    assert secret not in resp.text
    request_id = resp.json()["request_id"]
    assert resp.headers["x-request-id"] == request_id

    record = next(r for r in caplog.records if r.getMessage() == "unhandled exception")
    line = JsonFormatter().format(record)
    assert secret not in line
    assert '"exc_type": "RuntimeError"' in line and '"frames": ["' in line
    assert record.request_id == request_id  # type: ignore[attr-defined]
    access = next(r for r in caplog.records if r.getMessage() == "request")
    assert access.status == 500 and access.request_id == request_id  # type: ignore[attr-defined]


async def test_enrichment_row_unchanged_after_failed_reenrich(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    use_enricher(client, _Enricher(ValueError("x")))
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 502
    kept = (await db.execute(select(Enrichment))).scalars().one()
    assert kept.summary == "summary of s1"
