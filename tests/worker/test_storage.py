"""The real S3 store against the compose object store (S3_ENDPOINT_URL)."""

import uuid

import pytest
from sqlalchemy import select

from session_lens.config import Settings
from session_lens.db.models import RawRecording
from session_lens.storage.base import RecordingExpired
from session_lens.storage.s3 import S3Store
from session_lens.worker.queue import read_raw, store_raw
from tests.worker.helpers import recording


async def test_put_get_delete_roundtrip(s3_store):
    key = f"recordings/test-{uuid.uuid4().hex}/a.jsonl"
    data = b'{"v":1}\n' * 1000
    await s3_store.put(key, data)
    assert await s3_store.get(key) == data
    await s3_store.delete(key)
    await s3_store.delete(key)  # idempotent
    with pytest.raises(RecordingExpired):
        await s3_store.get(key)


async def test_17_mib_object_roundtrip(s3_store):
    key = f"recordings/test-{uuid.uuid4().hex}/big.jsonl"
    line = b'{"v":1,"pad":"' + b"x" * 1000 + b'"}\n'
    data = line * (17 * 1024 * 1024 // len(line) + 1)
    assert len(data) > 17 * 1024 * 1024
    await s3_store.put(key, data)
    assert await s3_store.get(key) == data
    await s3_store.delete(key)


async def test_store_raw_roundtrip_through_s3(sm, s3_store):
    async with sm() as db:
        raw = await store_raw(db, s3_store, recording("via-s3"))
        await db.commit()
        assert await read_raw(db, s3_store, raw.id) == recording("via-s3")


async def test_failed_put_leaves_no_row(sm):
    """A put the server rejects (bad credentials) must not leave a raw_recordings row."""
    settings = Settings()
    broken = S3Store(
        settings.s3_endpoint_url,
        settings.s3_region,
        settings.s3_bucket,
        settings.s3_access_key,
        "not-the-secret",
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


async def test_get_missing_key_is_recording_expired(s3_store):
    with pytest.raises(RecordingExpired):
        await s3_store.get(f"recordings/test-{uuid.uuid4().hex}/nope.jsonl")


async def test_ping(s3_store):
    await s3_store.ping()


async def test_ping_fails_when_unreachable():
    bad = S3Store("http://127.0.0.1:1", "us-east-1", "x", "a", "b", connect_timeout=1)
    try:
        with pytest.raises(Exception):  # noqa: B017
            await bad.ping()
    finally:
        await bad.aclose()


async def test_one_client_is_reused_and_aclose_is_idempotent(s3_store):
    await s3_store.ping()
    first = s3_store._client
    await s3_store.ping()
    assert s3_store._client is first
    await s3_store.aclose()
    await s3_store.aclose()
    await s3_store.ping()  # reopens lazily


async def test_expiry_days_reads_the_lifecycle_rule(s3_store):
    # s3-init applies a 30-day rule on recordings/
    assert await s3_store.expiry_days("recordings/") == 30
    assert await s3_store.expiry_days("recordings/test-x/") == 30
    assert await s3_store.expiry_days("elsewhere/") is None
