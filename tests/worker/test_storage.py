"""The real S3 store against the compose object store (S3_ENDPOINT_URL)."""

import uuid

import pytest

from session_lens.storage.base import RecordingExpired
from session_lens.storage.s3 import S3Store


async def test_put_get_delete_roundtrip(s3_store):
    key = f"recordings/test-{uuid.uuid4().hex}/a.jsonl"
    data = b'{"v":1}\n' * 1000
    await s3_store.put(key, data)
    assert await s3_store.get(key) == data
    await s3_store.delete(key)
    await s3_store.delete(key)  # idempotent
    with pytest.raises(RecordingExpired):
        await s3_store.get(key)


async def test_get_missing_key_is_recording_expired(s3_store):
    with pytest.raises(RecordingExpired):
        await s3_store.get(f"recordings/test-{uuid.uuid4().hex}/nope.jsonl")


async def test_ping(s3_store):
    await s3_store.ping()


async def test_ping_fails_when_unreachable():
    bad = S3Store("http://127.0.0.1:1", "us-east-1", "x", "a", "b")
    with pytest.raises(Exception):  # noqa: B017
        await bad.ping()
