"""FastAPI dependencies: settings, database session, bearer-token auth, queue and enricher."""

import secrets
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.config import Settings
from session_lens.db.models import Batch, RawRecording

if TYPE_CHECKING:
    from session_lens.enrich.base import Enricher, EnrichmentResult
    from session_lens.storage.base import RecordingStore

_bearer = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def require_token(
    settings: Annotated[Settings, Depends(get_app_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    supplied = credentials.credentials if credentials else ""
    if not credentials or not secrets.compare_digest(
        supplied.encode(), settings.api_token.encode()
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


class QueueApi(Protocol):
    """The slice of `worker/` the API uses (see docs/contracts.md)."""

    async def create_batch(
        self,
        session: AsyncSession,
        store: "RecordingStore",
        files: Sequence[tuple[str, RawRecording]],
    ) -> Batch: ...

    async def store_raw(
        self, session: AsyncSession, store: "RecordingStore", data: bytes
    ) -> RawRecording: ...

    async def retry_failed(self, session: AsyncSession, batch_id: int) -> object: ...

    async def cancel_batch(self, session: AsyncSession, batch_id: int) -> object: ...

    async def read_raw(
        self, session: AsyncSession, store: "RecordingStore", raw_id: int
    ) -> bytes: ...

    async def delete_raws_for_hash(
        self, session: AsyncSession, store: "RecordingStore", content_hash: str
    ) -> int: ...

    async def upsert_enrichment(
        self, session: AsyncSession, session_id: int, result: "EnrichmentResult"
    ) -> None: ...


class _WorkerQueue:
    """Adapter over the worker modules, imported lazily so the API can load without them."""

    async def create_batch(
        self,
        session: AsyncSession,
        store: "RecordingStore",
        files: Sequence[tuple[str, RawRecording]],
    ) -> Batch:
        from session_lens.worker import queue

        result: Batch = await queue.create_batch(session, store, files)
        return result

    async def store_raw(
        self, session: AsyncSession, store: "RecordingStore", data: bytes
    ) -> RawRecording:
        from session_lens.worker import queue

        raw: RawRecording = await queue.store_raw(session, store, data)
        return raw

    async def retry_failed(self, session: AsyncSession, batch_id: int) -> object:
        from session_lens.worker import queue

        return await queue.retry_failed(session, batch_id)

    async def cancel_batch(self, session: AsyncSession, batch_id: int) -> object:
        from session_lens.worker import queue

        return await queue.cancel_batch(session, batch_id)

    async def read_raw(self, session: AsyncSession, store: "RecordingStore", raw_id: int) -> bytes:
        from session_lens.worker import queue

        data: bytes = await queue.read_raw(session, store, raw_id)
        return data

    async def delete_raws_for_hash(
        self, session: AsyncSession, store: "RecordingStore", content_hash: str
    ) -> int:
        from session_lens.worker import queue

        count: int = await queue.delete_raws_for_hash(session, store, content_hash)
        return count

    async def upsert_enrichment(
        self, session: AsyncSession, session_id: int, result: "EnrichmentResult"
    ) -> None:
        from session_lens.worker.processor import upsert_enrichment

        await upsert_enrichment(session, session_id, result)


def get_queue() -> QueueApi:
    return _WorkerQueue()


def get_store(request: Request) -> "RecordingStore":
    """The object store, built once on first use and kept on the app."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        from session_lens.storage.base import build_store

        store = request.app.state.store = build_store(request.app.state.settings)
    return store


def get_enricher(settings: Annotated[Settings, Depends(get_app_settings)]) -> "Enricher":
    from session_lens.enrich.base import build_enricher

    return build_enricher(settings)
