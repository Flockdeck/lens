"""Storage for raw recordings: files on the local filesystem."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lens.config import Settings


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
    """The store for raw recordings: files under `data_dir`. Call `await store.aclose()` on
    shutdown."""
    from lens.storage.filesystem import FilesystemStore

    return FilesystemStore(Path(settings.data_dir).expanduser())
