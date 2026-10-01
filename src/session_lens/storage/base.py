"""Storage for raw recordings: the local filesystem by default, S3 optionally."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from session_lens.config import Settings


class RecordingExpired(Exception):
    """The recording's file is gone (retention or deletion), or its row says so."""


class RecordingStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes:
        """Raises RecordingExpired if there is no such object."""
        ...

    async def delete(self, key: str) -> None:
        """Idempotent."""
        ...

    async def ping(self) -> None:
        """For /readyz. Raises if the store is unusable."""
        ...

    async def aclose(self) -> None:
        """Release the connection pool. Call once at shutdown (worker, cleanup, API lifespan)."""
        ...


def build_store(settings: Settings) -> RecordingStore:
    """The configured store: the local filesystem (default) or S3. Call `await store.aclose()`
    on shutdown."""
    if settings.storage == "s3":
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
    from session_lens.storage.filesystem import FilesystemStore

    return FilesystemStore(Path(settings.data_dir))
