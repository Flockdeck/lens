"""The whole flow through the real stack:
upload, queue, parse, enrich, store, read, expire, delete."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from session_lens.worker.cleanup import run_cleanup
from tests.e2e.conftest import MAX_FILE_BYTES, Stack, jsonl_line, recording


async def test_submit_process_and_read_everything(stack: Stack) -> None:
    submitted = [
        ("claude_full.jsonl", recording("claude_full", "a")),
        ("truncated.jsonl", recording("truncated", "b")),
        ("cut_off_last_line.jsonl", recording("cut_off_last_line", "c")),
        ("chat_client.jsonl", recording("chat_client", "d")),
        ("start_stop_only.jsonl", recording("start_stop_only", "e")),
        ("unknown_types_and_fields.jsonl", recording("unknown_types_and_fields", "f")),
        ("wrong_version.jsonl", recording("wrong_version")),
        ("empty.jsonl", recording("empty")),
    ]
    accepted = await stack.upload(*submitted)

    # the upload answers at once, naming what it kept and what it refused, and why
    assert len(accepted["accepted"]) == 7
    assert [r["filename"] for r in accepted["rejected"]] == ["empty.jsonl"]
    assert "empty" in accepted["rejected"][0]["reason"].lower()

    batch = await stack.wait_for_batch(accepted["id"])
    assert batch["status"] == "done"
    assert batch["counts"] == {"queued": 0, "running": 0, "done": 6, "failed": 1, "cancelled": 0}
    items = {i["filename"]: i for i in batch["items"]}
    assert items["wrong_version.jsonl"]["status"] == "failed"
    assert items["wrong_version.jsonl"]["error"] == (
        "UnsupportedVersion: recording format version 2 is not supported"
    )
    assert items["wrong_version.jsonl"]["session_id"] is None
    assert all(i["session_id"] for n, i in items.items() if n != "wrong_version.jsonl")

    # every recording that parsed became a session with computed facts and an enrichment
    listing = await stack.sessions()
    assert listing["total"] == 6
    by_agent = {s["agent"] for s in listing["items"]}
    assert {"claude", "claude-api", "codex"} <= by_agent
    for s in listing["items"]:
        assert s["raw_available"] is True
        assert s["outcome"] in {"done", "abandoned", "stuck"}
        assert s["summary"]
    completeness = {
        s["recording_session"].rsplit("-", 1)[-1]: s["completeness"] for s in listing["items"]
    }
    assert completeness["a"] == "clean"
    assert completeness["b"] == "truncated"
    assert completeness["c"] == "cut_off"
    assert completeness["e"] == "partial_agent"

    # the Claude recording in detail: metrics, rules and the enrichment
    claude = next(s for s in listing["items"] if s["recording_session"].endswith("-a"))
    detail = await stack.session(claude["id"])
    assert detail["metrics"]["tool_calls"] == 9
    assert detail["metrics"]["tool_errors"] == 2
    rules = {r["rule"]: r["severity"] for r in detail["risky_actions"]}
    assert rules["git_force_push"] == "high"
    assert detail["enrichment"]["outcome"] == "stuck"
    assert detail["enrichment"]["stuck_points"]
    assert detail["enrichment"]["model"] == "mock"
    assert detail["files_touched"]["commands"]

    # the events view pages through the stored recording and keeps Flockdeck's own field names
    events = await stack.all_events(claude["id"], page=4)
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and len(events) >= 9
    assert any("toolUseId" in e for e in events)

    # raw recordings are on disk, one file per accepted upload, and nowhere else
    assert len(stack.raw_files()) == 7
    assert await stack.scalar("SELECT COUNT(*) FROM raw_recordings") == 7

    # the read side: stats, config, privacy headers
    trends = (await stack.client.get("/stats/trends", params={"interval": "day"})).json()
    assert trends and sum(sum(b["outcomes"].values()) for b in trends) == 6
    compare = (await stack.client.get("/stats/compare", params={"by": "agent"})).json()
    assert {row["key"] for row in compare} >= {"claude", "claude-api", "codex"}
    usage = (await stack.client.get("/stats/usage")).json()
    assert usage["enrichments"] == 6
    config = (await stack.client.get("/config")).json()
    assert (config["storage"], config["enricher"], config["raw_retention_days"]) == (
        "filesystem",
        "mock",
        30,
    )
    resp = await stack.client.get("/sessions")
    assert resp.headers["cache-control"] == "no-store"


async def test_resubmitting_is_free_and_a_longer_recording_replaces_the_session(
    stack: Stack,
) -> None:
    original = recording("claude_full", "grow")
    first = await stack.upload(("run.jsonl", original))
    await stack.wait_for_batch(first["id"])
    (session,) = (await stack.sessions())["items"]
    hash_before = await stack.scalar(
        "SELECT content_hash FROM sessions WHERE id = :i", i=session["id"]
    )

    # identical bytes again: the same session, nothing duplicated
    second = await stack.upload(("run.jsonl", original))
    again = await stack.wait_for_batch(second["id"])
    assert again["counts"]["done"] == 1
    listing = await stack.sessions()
    assert listing["total"] == 1 and listing["items"][0]["id"] == session["id"]

    # the same recording grown by an event: still one session, with the new event and a new hash
    last = max(json.loads(line)["seq"] for line in original.splitlines() if line.strip())
    first_event = json.loads(original.splitlines()[0])
    longer = original + jsonl_line(
        v=1,
        seq=last + 1,
        time="2026-10-01T12:00:00Z",
        session=first_event["session"],
        pane=first_event["pane"],
        agent="claude",
        type="user_prompt",
        text="one more thing",
    )
    third = await stack.upload(("run.jsonl", longer))
    await stack.wait_for_batch(third["id"])
    listing = await stack.sessions()
    assert listing["total"] == 1 and listing["items"][0]["id"] == session["id"]
    events = await stack.all_events(session["id"])
    assert events[-1]["seq"] == last + 1 and events[-1]["text"] == "one more thing"
    hash_after = await stack.scalar(
        "SELECT content_hash FROM sessions WHERE id = :i", i=session["id"]
    )
    assert hash_after != hash_before
    assert await stack.scalar("SELECT COUNT(*) FROM enrichments") == 1


async def test_retention_removes_raw_files_but_keeps_what_was_derived(stack: Stack) -> None:
    batch = await stack.upload(
        ("old.jsonl", recording("claude_full", "old")),
        ("recent.jsonl", recording("truncated", "recent")),
    )
    await stack.wait_for_batch(batch["id"])
    by_name = {
        s["recording_session"].rsplit("-", 1)[-1]: s for s in (await stack.sessions())["items"]
    }
    old, recent = by_name["old"], by_name["recent"]
    assert len(stack.raw_files()) == 2

    # the old upload is 40 days old: past the 30-day retention
    long_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40)
    async with stack.sm() as db:
        await db.execute(
            text(
                "UPDATE raw_recordings SET created_at = :t "
                "WHERE id = (SELECT raw_id FROM sessions WHERE id = :i)"
            ),
            {"t": long_ago, "i": old["id"]},
        )
        await db.commit()

    result = await run_cleanup(stack.sm, stack.store, stack.settings.raw_retention_days)
    assert result.raws_expired == 1 and not result.skipped
    assert len(stack.raw_files()) == 1  # the file is really gone, not just marked

    expired = await stack.session(old["id"])
    assert expired["raw_available"] is False
    assert expired["metrics"]["tool_calls"] == 9 and expired["enrichment"]["outcome"] == "stuck"
    assert (await stack.client.get(f"/sessions/{old['id']}/events")).status_code == 410
    assert (await stack.client.post(f"/sessions/{old['id']}/enrich")).status_code == 410

    kept = await stack.session(recent["id"])
    assert kept["raw_available"] is True
    assert (await stack.client.get(f"/sessions/{recent['id']}/events")).status_code == 200
    assert (await stack.client.post(f"/sessions/{recent['id']}/enrich")).status_code == 200

    # a second run finds nothing more to do
    again = await run_cleanup(stack.sm, stack.store, stack.settings.raw_retention_days)
    assert again.raws_expired == 0


async def test_deleting_a_session_removes_its_files_too(stack: Stack) -> None:
    batch = await stack.upload(
        ("a.jsonl", recording("claude_full", "del-a")),
        ("b.jsonl", recording("truncated", "del-b")),
    )
    await stack.wait_for_batch(batch["id"])
    first, second = (await stack.sessions())["items"]
    assert len(stack.raw_files()) == 2

    assert (await stack.client.delete(f"/sessions/{first['id']}")).status_code == 204
    assert (await stack.client.get(f"/sessions/{first['id']}")).status_code == 404
    assert len(stack.raw_files()) == 1
    assert await stack.scalar("SELECT COUNT(*) FROM enrichments") == 1
    assert (await stack.client.get(f"/sessions/{second['id']}")).status_code == 200
    assert (await stack.sessions())["total"] == 1


async def test_cancel_stops_queued_items_and_retry_requeues_failures(stack: Stack) -> None:
    await stack.stop_worker()  # nothing runs, so everything submitted stays queued
    queued = await stack.upload(
        *[(f"f{i}.jsonl", recording("claude_full", f"q{i}")) for i in range(5)]
    )
    assert (await stack.batch(queued["id"]))["counts"]["queued"] == 5

    resp = await stack.client.post(f"/batches/{queued['id']}/cancel")
    assert resp.status_code in (200, 204), resp.text
    cancelled = await stack.batch(queued["id"])
    assert cancelled["status"] == "cancelled" and cancelled["counts"]["cancelled"] == 5

    stack.start_worker()
    failing = await stack.upload(("wrong_version.jsonl", recording("wrong_version")))
    done = await stack.wait_for_batch(failing["id"])
    assert done["counts"]["failed"] == 1
    # the cancelled batch's items were never run
    assert (await stack.batch(queued["id"]))["counts"]["cancelled"] == 5
    assert (await stack.sessions())["total"] == 0

    # retry re-queues the failure; a permanent failure fails again, with the same reason
    resp = await stack.client.post(f"/batches/{failing['id']}/retry")
    assert resp.status_code in (200, 204), resp.text
    retried = await stack.wait_for_batch(failing["id"])
    assert retried["counts"]["failed"] == 1
    assert retried["items"][0]["error"].startswith("UnsupportedVersion")


async def test_uploads_are_checked_one_file_at_a_time(stack: Stack) -> None:
    too_big = recording("claude_full", "big") + b"\n" * (MAX_FILE_BYTES + 10)
    body = await stack.upload(
        ("fine.jsonl", recording("claude_full", "fine")),
        ("notes.txt", b"not a recording"),
        ("big.jsonl", too_big),
        ("empty.jsonl", b""),
    )
    assert [a for a in body["accepted"]] == ["fine.jsonl"]
    reasons = {r["filename"]: r["reason"].lower() for r in body["rejected"]}
    assert set(reasons) == {"notes.txt", "big.jsonl", "empty.jsonl"}
    assert "large" in reasons["big.jsonl"] or "size" in reasons["big.jsonl"]
    done = await stack.wait_for_batch(body["id"])
    assert done["counts"]["done"] == 1
    assert len(stack.raw_files()) == 1  # a refused file is never stored

    nothing = await stack.client.post(
        "/batches", files=[("files", ("empty.jsonl", b"", "application/x-ndjson"))]
    )
    assert nothing.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/sessions"),
        ("GET", "/sessions/1"),
        ("GET", "/sessions/1/events"),
        ("POST", "/sessions/1/enrich"),
        ("DELETE", "/sessions/1"),
        ("GET", "/batches/1"),
        ("POST", "/batches/1/cancel"),
        ("POST", "/batches/1/retry"),
        ("GET", "/stats/trends"),
        ("GET", "/stats/compare"),
        ("GET", "/stats/usage"),
        ("GET", "/config"),
    ],
)
async def test_every_data_endpoint_needs_the_token(stack: Stack, method: str, path: str) -> None:
    resp = await stack.anonymous.request(method, path)
    assert resp.status_code == 401
    wrong = await stack.anonymous.request(method, path, headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


async def test_health_endpoints_work_without_a_token_and_say_the_stack_is_ready(
    stack: Stack,
) -> None:
    assert (await stack.anonymous.get("/healthz")).status_code == 200
    assert (await stack.anonymous.get("/readyz")).status_code == 200
    assert "text/plain" in (await stack.anonymous.get("/metrics")).headers["content-type"]
