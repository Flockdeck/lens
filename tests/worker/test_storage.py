"""The store contract, run against every real implementation: the filesystem store always, the
optional S3 store when S3_ENDPOINT_URL points at a reachable server (`docker compose --profile s3`).
"""

import uuid

import pytest
from sqlalchemy import select

from session_lens.config import Settings
from session_lens.db.models import RawRecording
from session_lens.storage.base import RecordingExpired
from session_lens.worker.queue import read_raw, store_raw
from tests.worker.helpers import recording


def key() -> str:
    return f"recordings/test-{uuid.uuid4().hex}/a.jsonl"


async def test_put_get_delete_roundtrip(any_store):
    k = key()
    data = b'{"v":1}\n' * 1000
    await any_store.put(k, data)
    assert await any_store.get(k) == data
    await any_store.delete(k)
    await any_store.delete(k)  # idempotent
    with pytest.raises(RecordingExpired):
        await any_store.get(k)


async def test_17_mib_object_roundtrip(any_store):
    k = key()
    line = b'{"v":1,"pad":"' + b"x" * 1000 + b'"}\n'
    data = line * (17 * 1024 * 1024 // len(line) + 1)
    assert len(data) > 17 * 1024 * 1024
    await any_store.put(k, data)
    assert await any_store.get(k) == data
    await any_store.delete(k)


async def test_store_raw_roundtrip(sm, any_store):
    async with sm() as db:
        raw = await store_raw(db, any_store, recording("via-store"))
        await db.commit()
        assert await read_raw(db, any_store, raw.id) == recording("via-store")


async def test_get_missing_key_is_recording_expired(any_store):
    with pytest.raises(RecordingExpired):
        await any_store.get(key())


async def test_ping(any_store):
    await any_store.ping()


async def test_failed_put_leaves_no_row(sm, store):
    store.fail_put = True
    async with sm() as db:
        with pytest.raises(OSError):
            await store_raw(db, store, recording())
        await db.rollback()
    async with sm() as db:
        assert (await db.execute(select(RawRecording))).first() is None


# --- S3-only behaviour -------------------------------------------------------------------


async def test_s3_failed_put_leaves_no_row(sm, s3_store):
    """A put the server rejects (bad credentials) must not leave a raw_recordings row."""
    from session_lens.storage.s3 import S3Store

    settings = Settings(storage="s3")
    broken = S3Store(
        settings.s3_endpoint_url,
        settings.s3_region,
        settings.s3_bucket,
        settings.s3_access_key,
        "not-the-secret",
        addressing_style=settings.s3_addressing_style,
    )
    try:
        async with sm() as db:
            with pytest.raises(Exception):  # noqa: B017
                await store_raw(db, broken, recording())
            await db.rollback()
        async with sm() as db:
            assert (await db.execute(select(RawRecording))).first() is None
    finally:
        await broken.aclose()


async def test_s3_ping_fails_when_unreachable():
    pytest.importorskip("aioboto3")
    from session_lens.storage.s3 import S3Store

    bad = S3Store("http://127.0.0.1:1", "us-east-1", "x", "a", "b", connect_timeout=1)
    try:
        with pytest.raises(Exception):  # noqa: B017
            await bad.ping()
    finally:
        await bad.aclose()


async def test_s3_one_client_is_reused_and_aclose_is_idempotent(s3_store):
    await s3_store.ping()
    first = s3_store._client
    await s3_store.ping()
    assert s3_store._client is first
    await s3_store.aclose()
    await s3_store.aclose()
    await s3_store.ping()  # reopens lazily


async def test_s3_expiry_days_reads_the_lifecycle_rule(s3_store):
    # s3-init applies a 30-day rule on recordings/
    assert await s3_store.expiry_days("recordings/") == 30
    assert await s3_store.expiry_days("recordings/test-x/") == 30
    assert await s3_store.expiry_days("elsewhere/") is None
