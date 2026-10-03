"""The store contract, run against every real implementation: the filesystem store always, the"""

import uuid

import pytest
from sqlalchemy import select

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
