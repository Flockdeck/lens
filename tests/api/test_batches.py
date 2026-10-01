from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.db.models import BatchItem, ItemStatus, RawRecording


def files(*parts: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, data, "application/octet-stream")) for name, data in parts]


async def test_submit_mixed_batch(
    client: httpx.AsyncClient, db: AsyncSession, make_jsonl: Any
) -> None:
    resp = await client.post(
        "/batches",
        files=files(
            ("a.jsonl", make_jsonl(1, 2)),
            ("../../sneaky/b.JSONL", make_jsonl(1)),
            ("notes.txt", b"hello"),
            ("empty.jsonl", b"  \n"),
            ("big.jsonl", b"x" * 2000),
        ),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == ["a.jsonl", "b.JSONL"]
    reasons = {r["filename"]: r["reason"] for r in body["rejected"]}
    assert reasons["notes.txt"].startswith("wrong type")
    assert reasons["empty.jsonl"] == "empty"
    assert reasons["big.jsonl"].startswith("too large")

    assert len((await db.execute(select(RawRecording))).scalars().all()) == 2

    detail = (await client.get(f"/batches/{body['id']}")).json()
    assert detail["counts"] == {"queued": 2, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    assert [i["filename"] for i in detail["items"]] == ["a.jsonl", "b.JSONL"]
    assert set(detail["items"][0]) == {
        "id",
        "filename",
        "status",
        "attempts",
        "error",
        "session_id",
    }


async def test_nothing_accepted_is_422(client: httpx.AsyncClient, db: AsyncSession) -> None:
    resp = await client.post("/batches", files=files(("a.txt", b"x"), ("b.jsonl", b"")))
    assert resp.status_code == 422
    assert len(resp.json()["rejected"]) == 2
    assert (await db.execute(select(RawRecording))).first() is None


async def test_no_files_field_is_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/batches", data={"other": "x"})
    assert resp.status_code == 422


async def test_too_many_files_is_400(client: httpx.AsyncClient, make_jsonl: Any) -> None:
    parts = [(f"{i}.jsonl", make_jsonl(1)) for i in range(6)]
    assert (await client.post("/batches", files=files(*parts))).status_code == 400


async def test_declared_request_size_limit(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/batches",
        files=files(("a.jsonl", b"x" * 900)),
        headers={"Content-Length": "999999"},
    )
    assert resp.status_code == 413


async def test_batch_not_found(client: httpx.AsyncClient) -> None:
    for method, path in (("GET", ""), ("POST", "/retry"), ("POST", "/cancel")):
        assert (await client.request(method, f"/batches/999{path}")).status_code == 404


async def test_cancel_then_retry(
    client: httpx.AsyncClient, db: AsyncSession, make_jsonl: Any
) -> None:
    resp = await client.post(
        "/batches", files=files(("a.jsonl", make_jsonl(1)), ("b.jsonl", make_jsonl(2)))
    )
    batch_id = resp.json()["id"]

    cancelled = (await client.post(f"/batches/{batch_id}/cancel")).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["counts"]["cancelled"] == 2

    item = (await db.execute(select(BatchItem).order_by(BatchItem.id))).scalars().first()
    assert item is not None
    item.status = ItemStatus.failed
    item.error = "boom"
    await db.commit()

    retried = (await client.post(f"/batches/{batch_id}/retry")).json()
    assert retried["counts"]["queued"] == 1
    assert retried["items"][0]["error"] is None
