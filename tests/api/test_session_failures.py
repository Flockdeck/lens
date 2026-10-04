"""What the session endpoints do when something is missing or fails."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from lens.api.deps import get_enricher_provider
from lens.enrich.base import EnrichmentError
from lens.recording.models import Analysis
from lens.storage.memory import InMemoryStore
from tests.api.test_sessions import seed


class _Failing:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def enrich(self, analysis: Analysis) -> Any:
        raise self.exc


def use_enricher(client: httpx.AsyncClient, enricher: object) -> None:
    client.app.dependency_overrides[get_enricher_provider] = lambda: lambda: enricher  # type: ignore[attr-defined]


async def test_unknown_sessions_are_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/sessions/999")).status_code == 404
    assert (await client.get("/sessions/999/events")).status_code == 404
    assert (await client.post("/sessions/999/enrich")).status_code == 404
    assert (await client.delete("/sessions/999")).status_code == 404


async def test_a_retryable_enrichment_failure_is_503(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "r1", raw=make_jsonl(1, 2))
    use_enricher(client, _Failing(EnrichmentError("rate limited", retryable=True)))
    resp = await client.post(f"/sessions/{row.id}/enrich")
    assert resp.status_code == 503
    assert "rate limited" not in resp.text  # the cause is logged, not echoed


async def test_a_permanent_enrichment_failure_is_502(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "r2", raw=make_jsonl(1, 2))
    use_enricher(client, _Failing(EnrichmentError("refused", retryable=False)))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == 502


async def test_an_enricher_that_crashes_is_502_and_leaks_nothing(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "r3", raw=make_jsonl(1, 2))
    use_enricher(client, _Failing(RuntimeError("SECRET-FROM-THE-MODEL")))
    resp = await client.post(f"/sessions/{row.id}/enrich")
    assert resp.status_code == 502
    assert "SECRET" not in resp.text


async def test_a_recording_that_cannot_be_parsed_is_422(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    row = await seed(db, store, "r4", raw=b"this is not json\nnor is this\n")
    resp = await client.post(f"/sessions/{row.id}/enrich")
    assert resp.status_code == 422


async def test_a_raw_file_that_vanished_is_410_and_remembered(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "r5", raw=make_jsonl(1, 2, 3))
    assert (await client.get(f"/sessions/{row.id}")).json()["raw_available"] is True
    store.objects.clear()  # removed behind the app's back
    assert (await client.get(f"/sessions/{row.id}/events")).status_code == 410
    # the miss was recorded, so the session now says so without touching the store again
    assert (await client.get(f"/sessions/{row.id}")).json()["raw_available"] is False
    assert (await client.get(f"/sessions/{row.id}/events")).status_code == 410


async def test_deleting_a_session_deletes_its_raw_file(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "r6", raw=make_jsonl(1, 2))
    assert len(store.objects) == 1
    assert (await client.delete(f"/sessions/{row.id}")).status_code == 204
    assert store.objects == {}
    assert (await client.get(f"/sessions/{row.id}")).status_code == 404
    assert (await client.delete(f"/sessions/{row.id}")).status_code == 404
