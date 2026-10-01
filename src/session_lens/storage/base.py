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

    async def expiry_days(self, prefix: str) -> int | None:
        """Days after which the bucket's lifecycle rules expire objects under `prefix`
        (the shortest enabled rule that covers it), or None if there is no such rule."""
        ...

    async def aclose(self) -> None:
        """Release the connection pool. Call once at shutdown (worker, cleanup, API lifespan)."""
        ...


def build_store(settings: Settings) -> RecordingStore:
    """An S3 store (Spaces / MinIO / SeaweedFS). The client is opened lazily and kept for the
    store's lifetime: call `await store.aclose()` on shutdown."""
    from session_lens.storage.s3 import S3Store

    return S3Store(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        addressing_style=settings.s3_addressing_style,
        connect_timeout=settings.s3_connect_timeout,
        read_timeout=settings.s3_read_timeout,
    )
