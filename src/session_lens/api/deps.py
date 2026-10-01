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
    from session_lens.enrich.base import Enricher

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
    """The slice of `worker/queue.py` the API uses (see docs/contracts.md)."""

    async def create_batch(
        self, session: AsyncSession, files: Sequence[tuple[str, RawRecording]]
    ) -> Batch: ...

    async def retry_failed(self, session: AsyncSession, batch_id: int) -> object: ...

    async def cancel_batch(self, session: AsyncSession, batch_id: int) -> object: ...

    async def store_raw(self, session: AsyncSession, data: bytes) -> RawRecording: ...


class _WorkerQueue:
    """Adapter over the worker module, imported lazily so the API can load without it."""

    async def create_batch(
        self, session: AsyncSession, files: Sequence[tuple[str, RawRecording]]
    ) -> Batch:
        from session_lens.worker import queue

        result: Batch = await queue.create_batch(session, files)
        return result

    async def retry_failed(self, session: AsyncSession, batch_id: int) -> object:
        from session_lens.worker import queue

        return await queue.retry_failed(session, batch_id)

    async def cancel_batch(self, session: AsyncSession, batch_id: int) -> object:
        from session_lens.worker import queue

        return await queue.cancel_batch(session, batch_id)

    async def store_raw(self, session: AsyncSession, data: bytes) -> RawRecording:
        from session_lens.worker import queue

        result: RawRecording = await queue.store_raw(session, data)
        return result


def get_queue() -> QueueApi:
    return _WorkerQueue()


def get_enricher(settings: Annotated[Settings, Depends(get_app_settings)]) -> "Enricher":
    from session_lens.enrich.base import build_enricher

    return build_enricher(settings)
