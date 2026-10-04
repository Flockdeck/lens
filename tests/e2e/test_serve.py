"""`lens serve`: one process is the whole service, starting from nothing."""

from __future__ import annotations

import asyncio
import pathlib
import time

import httpx

from lens.api.app import create_app
from lens.config import Settings
from tests.e2e.conftest import recording


def serve_settings(data_dir: pathlib.Path) -> Settings:
    return Settings(
        data_dir=str(data_dir),
        database_url="",
        allowed_hosts=["serve"],
        enricher="mock",
        worker_poll_seconds=0.05,
        cleanup_interval_seconds=0,
        shutdown_grace_seconds=2,
    )


async def wait_done(client: httpx.AsyncClient, batch_id: int) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body = (await client.get(f"/batches/{batch_id}")).json()
        if body["counts"]["queued"] == 0 and body["counts"]["running"] == 0:
            return body  # type: ignore[no-any-return]
        await asyncio.sleep(0.1)
    raise AssertionError("the batch did not finish")


async def test_an_empty_data_directory_becomes_a_working_service(tmp_path: pathlib.Path) -> None:
    data = tmp_path / "fresh install"  # does not exist yet, and has a space in its name
    app = create_app(serve_settings(data), run_worker=True)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://serve") as c,
    ):
        assert (await c.get("/readyz")).status_code == 200  # migrated on start
        files = [
            ("files", ("run.jsonl", recording("claude_full", "serve"), "application/x-ndjson"))
        ]
        resp = await c.post("/batches", files=files)
        assert resp.status_code == 202, resp.text
        body = await wait_done(c, resp.json()["id"])  # the worker is inside this process
        assert body["counts"]["done"] == 1
        sessions = (await c.get("/sessions")).json()
        assert sessions["total"] == 1 and sessions["items"][0]["outcome"]
    assert (data / "lens.db").exists()
    assert any((data / "recordings").rglob("*.jsonl"))


async def test_everything_is_still_there_after_a_restart(tmp_path: pathlib.Path) -> None:
    settings = serve_settings(tmp_path / "data")
    for round_ in (1, 2):
        app = create_app(settings, run_worker=True)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://serve") as c,
        ):
            if round_ == 1:
                files = [
                    ("files", ("a.jsonl", recording("claude_full", "r1"), "application/x-ndjson"))
                ]
                resp = await c.post("/batches", files=files)
                await wait_done(c, resp.json()["id"])
            sessions = (await c.get("/sessions")).json()
            assert sessions["total"] == 1  # the second start sees the first one's data
            detail = (await c.get(f"/sessions/{sessions['items'][0]['id']}")).json()
            assert detail["enrichment"] is not None
            if round_ == 2:
                events = await c.get(f"/sessions/{detail['id']}/events")
                assert events.status_code == 200  # the raw recording survived too


async def test_stopping_with_work_queued_leaves_it_to_finish_next_time(
    tmp_path: pathlib.Path,
) -> None:
    settings = serve_settings(tmp_path / "data").model_copy(update={"worker_poll_seconds": 3600.0})
    # A worker that polls once an hour never claims anything while the app is up...
    app = create_app(settings, run_worker=True)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://serve") as c,
    ):
        files = [("files", ("a.jsonl", recording("claude_full", "q"), "application/x-ndjson"))]
        batch_id = (await c.post("/batches", files=files)).json()["id"]
    # ...so the item is still queued when it stops, and a normal start finishes it.
    app = create_app(serve_settings(tmp_path / "data"), run_worker=True)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://serve") as c,
    ):
        assert (await wait_done(c, batch_id))["counts"]["done"] == 1
