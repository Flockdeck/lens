"""End-to-end fixtures: the real stack, in one process.

The real FastAPI app (through its ASGI interface), the real worker loop, real SQLite (built from the
Alembic migration by the shared `database_url` fixture), the real filesystem store in a temp
directory, the real parser and the mock enricher. Nothing between an upload and a result is faked.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from session_lens.api.app import create_app
from session_lens.config import Settings
from session_lens.db.session import make_engine, make_sessionmaker
from session_lens.enrich.base import Enricher, build_enricher
from session_lens.storage.base import RecordingStore, build_store
from session_lens.worker.loop import run_worker
from tests.dbutil import clear_tables

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_SESSION = b"20261001T101530Z-0123abcd"

MAX_FILE_BYTES = 64 * 1024


def recording(name: str, suffix: str | None = None) -> bytes:
    """A fixture recording, optionally given its own session id (they all share one)."""
    data = (FIXTURES / f"{name}.jsonl").read_bytes()
    if suffix:
        data = data.replace(FIXTURE_SESSION, FIXTURE_SESSION + b"-" + suffix.encode())
    return data


def make_settings(
    database_url: str, data_dir: pathlib.Path, hosts: tuple[str, ...] = ("e2e",)
) -> Settings:
    return Settings(
        database_url=database_url,
        allowed_hosts=list(hosts),
        data_dir=str(data_dir),
        enricher="mock",
        cleanup_interval_seconds=0,  # the tests run cleanup themselves
        worker_poll_seconds=0.05,
        worker_concurrency=4,
        shutdown_grace_seconds=2,
        max_file_bytes=MAX_FILE_BYTES,
        max_files_per_batch=20,
        max_request_bytes=2 * 1024 * 1024,
        raw_retention_days=30,
    )


@dataclass
class Stack:
    client: httpx.AsyncClient
    sm: async_sessionmaker[AsyncSession]
    store: RecordingStore
    enricher: Enricher
    settings: Settings
    data_dir: pathlib.Path
    _stop: asyncio.Event | None = field(default=None, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    # --- the worker -------------------------------------------------------------------
    def start_worker(self) -> None:
        assert self._task is None, "the worker is already running"
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            run_worker(self.sm, self.store, self.enricher, self.settings, self._stop)
        )

    async def stop_worker(self) -> None:
        if self._task is None or self._stop is None:
            return
        self._stop.set()
        await asyncio.wait_for(self._task, timeout=15)
        self._task, self._stop = None, None

    # --- the API, the way a client uses it ----------------------------------------------
    async def upload(self, *files: tuple[str, bytes]) -> dict[str, Any]:
        parts = [("files", (name, data, "application/x-ndjson")) for name, data in files]
        resp = await self.client.post("/batches", files=parts)
        assert resp.status_code == 202, resp.text
        body: dict[str, Any] = resp.json()
        return body

    async def batch(self, batch_id: int) -> dict[str, Any]:
        resp = await self.client.get(f"/batches/{batch_id}")
        assert resp.status_code == 200, resp.text
        body: dict[str, Any] = resp.json()
        return body

    async def wait_for_batch(self, batch_id: int, within: float = 30.0) -> dict[str, Any]:
        """Poll as the UI does, until nothing in the batch is queued or running."""
        deadline = time.monotonic() + within
        while True:
            body = await self.batch(batch_id)
            counts = body["counts"]
            if counts["queued"] == 0 and counts["running"] == 0:
                return body
            if time.monotonic() > deadline:
                raise AssertionError(f"batch {batch_id} did not finish: {counts}")
            await asyncio.sleep(0.1)

    async def sessions(self, **params: Any) -> dict[str, Any]:
        resp = await self.client.get("/sessions", params={"limit": 200, **params})
        assert resp.status_code == 200, resp.text
        body: dict[str, Any] = resp.json()
        return body

    async def session(self, session_id: int) -> dict[str, Any]:
        resp = await self.client.get(f"/sessions/{session_id}")
        assert resp.status_code == 200, resp.text
        body: dict[str, Any] = resp.json()
        return body

    async def all_events(self, session_id: int, page: int = 4) -> list[dict[str, Any]]:
        """Walk the events view page by page, the way the UI's 'Load more' does."""
        events: list[dict[str, Any]] = []
        after = 0
        while True:
            resp = await self.client.get(
                f"/sessions/{session_id}/events", params={"after_seq": after, "limit": page}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            events.extend(body["items"])
            if body["next_after_seq"] is None:
                return events
            after = body["next_after_seq"]

    # --- what is on disk and in the database -------------------------------------------
    def raw_files(self) -> list[pathlib.Path]:
        return sorted(p for p in self.data_dir.rglob("*") if p.is_file())

    async def scalar(self, sql: str, **params: Any) -> Any:
        async with self.sm() as db:
            return (await db.execute(text(sql), params)).scalar()


@pytest_asyncio.fixture
async def stack(database_url: str, tmp_path: pathlib.Path) -> AsyncIterator[Stack]:
    settings = make_settings(database_url, tmp_path / "data")
    engine: AsyncEngine = make_engine(settings)
    await clear_tables(engine)

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://e2e") as client:
            s = Stack(
                client=client,
                sm=make_sessionmaker(engine),
                store=build_store(settings),
                enricher=build_enricher(settings),
                settings=settings,
                data_dir=tmp_path / "data",
            )
            s.start_worker()
            try:
                yield s
            finally:
                await s.stop_worker()
    await engine.dispose()


def jsonl_line(**fields: Any) -> bytes:
    return json.dumps(fields).encode() + b"\n"
