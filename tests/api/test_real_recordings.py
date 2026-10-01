"""End-to-end through the API with the real parser, mock enricher and a real fixture file."""

from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.storage.memory import InMemoryStore
from tests.api.test_batches import files
from tests.api.test_sessions import seed

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_events_and_mock_reenrich_on_real_recording(
    client: httpx.AsyncClient, db: AsyncSession, store: InMemoryStore
) -> None:
    raw = (FIXTURES / "claude_full.jsonl").read_bytes()
    row = await seed(db, store, "real", raw=raw, outcome=None)

    page = (await client.get(f"/sessions/{row.id}/events", params={"limit": 5})).json()
    assert [e["seq"] for e in page["items"]] == [1, 2, 3, 4, 5]
    assert page["next_after_seq"] == 5
    assert page["items"][4]["toolUseId"] == "toolu_01"  # serialised with envelope aliases

    resp = await client.post(f"/sessions/{row.id}/enrich")  # default (mock) enricher
    assert resp.status_code == 200, resp.text
    enrichment = resp.json()["enrichment"]
    assert enrichment["model"] == "mock" and enrichment["outcome"] in {"done", "abandoned", "stuck"}
    assert resp.json()["category"] == enrichment["category"]


async def test_upload_real_fixture_then_malformed_file_is_accepted(
    client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    # Content is validated by the worker, not at upload: only size, type and emptiness here.
    resp = await client.post(
        "/batches",
        files=files(("wrong_version.jsonl", (FIXTURES / "wrong_version.jsonl").read_bytes())),
    )
    assert resp.status_code == 202 and len(store.objects) == 1
