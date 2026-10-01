"""Object storage for raw recordings."""

from __future__ import annotations

from typing import Protocol

from session_lens.config import Settings


class RecordingExpired(Exception):
    """The recording's object is gone (lifecycle rule or deletion), or its row says so."""


class RecordingStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes:
        """Raises RecordingExpired if there is no such object."""
        ...

    async def delete(self, key: str) -> None:
        """Idempotent."""
        ...

    async def ping(self) -> None:
        """For /readyz. Raises if the bucket is unreachable."""
        ...


def build_store(settings: Settings) -> RecordingStore:
    from session_lens.storage.s3 import S3Store

    return S3Store(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
