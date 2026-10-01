from datetime import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.deps import get_enricher
from session_lens.db.models import Enrichment, RawRecording
from session_lens.db.models import Session as SessionRow
from tests.api.standins import FakeQueue, InMemoryStore


async def seed(
    db: AsyncSession,
    store: InMemoryStore,
    recording: str,
    *,
    project: str = "proj",
    agent: str = "claude",
    model: str = "m1",
    started: datetime = datetime(2026, 1, 1, 12),
    outcome: str | None = "done",
    category: str = "bugfix",
    frustration: float = 0.2,
    raw: bytes | None = None,
    metrics: dict[str, Any] | None = None,
) -> SessionRow:
    raw_row = None
    if raw is not None:
        raw_row = await FakeQueue().store_raw(db, store, raw)
    row = SessionRow(
        recording_session=recording,
        content_hash=raw_row.content_hash if raw_row else "h" * 64,
        project=project,
        agent=agent,
        model=model,
        started_at=started,
        completeness="clean",
        metrics=metrics
        if metrics is not None
        else {"duration_seconds": 10.0, "tool_calls": 4, "tool_errors": 1},
        risky_actions=[],
        files_touched={"read": [], "edited": [], "commands": []},
        warnings=["w"],
        raw_id=raw_row.id if raw_row else None,
    )
    if outcome:
        row.enrichment = Enrichment(
            prompt_version="v1",
            model="mock",
            summary=f"summary of {recording}",
            category=category,
            outcome=outcome,
            frustration=frustration,
            input_tokens=100,
            output_tokens=10,
        )
    db.add(row)
    await db.commit()
    return row


def names(resp: httpx.Response) -> list[str]:
    return [i["recording_session"] for i in resp.json()["items"]]


async def test_list_filters_sort_paging(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    await seed(db, store, "s1", project="a", started=datetime(2026, 1, 1))
    await seed(
        db,
        store,
        "s2",
        project="a",
        agent="codex",
        outcome="stuck",
        category="docs",
        started=datetime(2026, 1, 5),
    )
    await seed(db, store, "s3", project="b", outcome=None, started=datetime(2026, 1, 9))

    body = (await client.get("/sessions")).json()
    assert body["total"] == 3
    assert [i["recording_session"] for i in body["items"]] == ["s3", "s2", "s1"]
    assert body["items"][0]["outcome"] is None and body["items"][0]["raw_available"] is False
    assert body["items"][1]["duration_seconds"] == 10.0

    assert names(await client.get("/sessions", params={"project": "a"})) == ["s2", "s1"]
    assert names(await client.get("/sessions", params={"agent": "codex"})) == ["s2"]
    assert names(await client.get("/sessions", params={"outcome": "stuck"})) == ["s2"]
    assert names(await client.get("/sessions", params={"category": "docs"})) == ["s2"]
    window = {"from": "2026-01-02", "to": "2026-01-06"}
    assert names(await client.get("/sessions", params=window)) == ["s2"]
    asc = {"sort": "started_at", "order": "asc"}
    assert names(await client.get("/sessions", params=asc)) == ["s1", "s2", "s3"]
    page = await client.get("/sessions", params={"limit": 1, "offset": 1})
    assert page.json()["total"] == 3 and names(page) == ["s2"]
    assert (await client.get("/sessions", params={"limit": 0})).status_code == 422
    assert (await client.get("/sessions", params={"sort": "bogus"})).status_code == 422


async def test_get_session_detail(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    row = await seed(db, store, "s1")
    body = (await client.get(f"/sessions/{row.id}")).json()
    assert body["warnings"] == ["w"]
    assert body["metrics"]["tool_calls"] == 4
    assert body["enrichment"]["summary"] == "summary of s1"
    assert (await client.get("/sessions/9999")).status_code == 404


async def test_events_paging(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "s1", raw=make_jsonl(1, 2, 3, 4, 5))
    url = f"/sessions/{row.id}/events"
    page = (await client.get(url, params={"limit": 2})).json()
    assert [e["seq"] for e in page["items"]] == [1, 2]
    assert page["next_after_seq"] == 2

    nxt = (await client.get(url, params={"limit": 2, "after_seq": 2})).json()
    assert [e["seq"] for e in nxt["items"]] == [3, 4]
    assert nxt["next_after_seq"] == 4

    tail = (await client.get(url, params={"after_seq": 4, "limit": 10})).json()
    assert [e["seq"] for e in tail["items"]] == [5]
    assert tail["next_after_seq"] is None

    exact = (await client.get(url, params={"after_seq": 3, "limit": 2})).json()
    assert [e["seq"] for e in exact["items"]] == [4, 5]
    assert exact["next_after_seq"] is None

    assert (await client.get("/sessions/9999/events")).status_code == 404


async def test_events_and_enrich_410_when_raw_gone(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    no_raw = await seed(db, store, "s1")
    assert (await client.get(f"/sessions/{no_raw.id}/events")).status_code == 410
    assert (await client.post(f"/sessions/{no_raw.id}/enrich")).status_code == 410
    assert (await client.get(f"/sessions/{no_raw.id}")).json()["raw_available"] is False

    # Row marked expired by `session-lens cleanup`.
    expired = await seed(db, store, "s2", raw=make_jsonl(1))
    await db.execute(update(RawRecording).values(expired_at=datetime(2026, 2, 1)))
    await db.commit()
    assert (await client.get(f"/sessions/{expired.id}")).json()["raw_available"] is False
    listed = (await client.get("/sessions")).json()["items"]
    assert all(i["raw_available"] is False for i in listed)
    assert (await client.get(f"/sessions/{expired.id}/events")).status_code == 410

    # Object removed by the bucket lifecycle rule before cleanup ran: still a 410.
    lost = await seed(db, store, "s3", raw=make_jsonl(1))
    assert (await client.get(f"/sessions/{lost.id}")).json()["raw_available"] is True
    store.objects.clear()
    assert (await client.get(f"/sessions/{lost.id}/events")).status_code == 410


class _Result:
    summary = "new summary"
    category = "feature"
    outcome = "stuck"
    frustration = 0.9
    stuck_points: list[Any] = []
    prompt_feedback = None
    risk_notes: list[Any] = []
    input_tokens = 5
    output_tokens = 6
    model = "fake"
    prompt_version = "v2"


class _Enricher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def enrich(self, analysis: object) -> _Result:
        if self.error:
            raise self.error
        return _Result()


def use_enricher(client: httpx.AsyncClient, enricher: _Enricher) -> None:
    client.app.dependency_overrides[get_enricher] = lambda: enricher  # type: ignore[attr-defined]


async def test_reenrich_overwrites(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    use_enricher(client, _Enricher())
    row = await seed(db, store, "s1", raw=make_jsonl(1, 2))
    body = (await client.post(f"/sessions/{row.id}/enrich")).json()
    assert body["enrichment"]["summary"] == "new summary"
    assert body["outcome"] == "stuck"
    assert len((await db.execute(select(Enrichment))).scalars().all()) == 1

    no_raw = await seed(db, store, "s2", outcome=None)
    assert (await client.post(f"/sessions/{no_raw.id}/enrich")).status_code == 410
    assert (await client.post("/sessions/9999/enrich")).status_code == 404


@pytest.mark.parametrize(("retryable", "code"), [(True, 503), (False, 502)])
async def test_reenrich_failure_codes(
    client: httpx.AsyncClient,
    db: AsyncSession,
    store: InMemoryStore,
    make_jsonl: Any,
    retryable: bool,
    code: int,
) -> None:
    from session_lens.enrich.base import EnrichmentError

    err = EnrichmentError("failed")
    err.retryable = retryable
    use_enricher(client, _Enricher(err))
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.post(f"/sessions/{row.id}/enrich")).status_code == code


async def test_delete_session(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore, make_jsonl: Any
) -> None:
    row = await seed(db, store, "s1", raw=make_jsonl(1))
    assert (await client.delete(f"/sessions/{row.id}")).status_code == 204
    assert (await client.get(f"/sessions/{row.id}")).status_code == 404
    assert (await db.execute(select(Enrichment))).first() is None
    assert (await db.execute(select(RawRecording))).first() is None
    assert store.objects == {}
    assert (await client.delete(f"/sessions/{row.id}")).status_code == 404


async def test_stats(client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore) -> None:
    await seed(
        db,
        store,
        "s1",
        started=datetime(2026, 1, 5),
        frustration=0.2,
        metrics={
            "tool_calls": 10,
            "tool_errors": 1,
            "permission": {"prompts": 4, "denied": 1},
        },
    )
    await seed(
        db,
        store,
        "s2",
        started=datetime(2026, 1, 6),
        outcome="stuck",
        frustration=0.6,
        metrics={
            "tool_calls": 10,
            "tool_errors": 3,
            "permission": {"prompts": 4, "denied": 3},
        },
    )
    await seed(
        db, store, "s3", agent="codex", started=datetime(2026, 1, 13), outcome=None, metrics={}
    )

    day = (await client.get("/stats/trends")).json()
    assert [d["bucket"] for d in day] == ["2026-01-05", "2026-01-06", "2026-01-13"]
    assert day[2]["outcomes"] == {"unenriched": 1} and day[2]["avg_frustration"] is None

    week = (await client.get("/stats/trends", params={"interval": "week"})).json()
    assert [w["bucket"] for w in week] == ["2026-01-05", "2026-01-12"]  # Mondays
    assert week[0]["sessions"] == 2
    assert week[0]["outcomes"] == {"done": 1, "stuck": 1}
    assert week[0]["avg_frustration"] == pytest.approx(0.4)
    assert week[0]["tool_error_rate"] == pytest.approx(0.2)

    assert (await client.get("/stats/trends", params={"project": "nope"})).json() == []

    by_agent = (await client.get("/stats/compare", params={"by": "agent"})).json()
    cmp_ = {c["key"]: c for c in by_agent}
    assert cmp_["claude"]["sessions"] == 2
    assert cmp_["claude"]["permission_denial_rate"] == pytest.approx(0.5)
    assert cmp_["codex"]["tool_error_rate"] is None
    by_model = (await client.get("/stats/compare", params={"by": "model"})).json()
    assert by_model[0]["key"] == "m1"
    assert (await client.get("/stats/compare", params={"by": "x"})).status_code == 422

    usage = (await client.get("/stats/usage")).json()
    assert usage == {"input_tokens": 200, "output_tokens": 20, "enrichments": 2}


async def test_empty_database(client: httpx.AsyncClient) -> None:
    usage = (await client.get("/stats/usage")).json()
    assert usage == {"input_tokens": 0, "output_tokens": 0, "enrichments": 0}
    assert (await client.get("/sessions")).json() == {"total": 0, "items": []}
    assert (await client.get("/stats/trends")).json() == []
    assert (await client.get("/stats/compare")).json() == []
