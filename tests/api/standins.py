"""Minimal local stand-ins for components built in parallel (worker, storage, recording, enrich).

Each is used only when the real module cannot be imported; once the components land, the
tests run against the real ones (with the in-memory store below in place of S3).
"""

import hashlib
import importlib
import json
import sys
import types
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.db.models import (
    Batch,
    BatchItem,
    BatchStatus,
    Enrichment,
    ItemStatus,
    RawRecording,
)


def importable(name: str) -> bool:
    try:
        importlib.import_module(name)
    except ImportError:
        return False
    return True


class StubRecordingExpired(Exception):
    pass


def install_stubs() -> None:
    """Register stub modules when the real ones are absent."""
    if not importable("session_lens.storage.base"):
        pkg: Any = types.ModuleType("session_lens.storage")
        pkg.__path__ = []
        base: Any = types.ModuleType("session_lens.storage.base")
        base.RecordingExpired = StubRecordingExpired
        base.build_store = lambda settings: InMemoryStore()
        sys.modules["session_lens.storage"] = pkg
        sys.modules["session_lens.storage.base"] = base
    if not importable("session_lens.recording.parser"):
        parser: Any = types.ModuleType("session_lens.recording.parser")
        parser.parse = _stub_parse
        parser.analyze = lambda events: types.SimpleNamespace(events=len(events))
        parser.UnsupportedVersion = type("UnsupportedVersion", (Exception,), {})
        parser.EmptyRecording = type("EmptyRecording", (Exception,), {})
        sys.modules["session_lens.recording.parser"] = parser
    if not importable("session_lens.enrich.base"):
        enrich: Any = types.ModuleType("session_lens.enrich.base")
        enrich.EnrichmentError = type("EnrichmentError", (Exception,), {"retryable": False})
        enrich.build_enricher = lambda settings: None
        sys.modules["session_lens.enrich.base"] = enrich


def expired_error() -> type[Exception]:
    from session_lens.storage.base import RecordingExpired

    return RecordingExpired


class InMemoryStore:
    """RecordingStore (docs/contracts.md) backed by a dict."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.healthy = True

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise expired_error()(key)
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def ping(self) -> None:
        if not self.healthy:
            raise ConnectionError("store down")


class StubEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    seq: int
    type: str


def _stub_parse(data: bytes) -> list[StubEvent]:
    return [StubEvent(**json.loads(line)) for line in data.splitlines() if line.strip()]


class FakeQueue:
    """Same signatures as the worker helpers in docs/contracts.md, minimal behaviour."""

    async def store_raw(self, session: AsyncSession, store: Any, data: bytes) -> RawRecording:
        key = f"recordings/{uuid.uuid4()}.jsonl"
        await store.put(key, data)
        raw = RawRecording(
            content_hash=hashlib.sha256(data).hexdigest(), size_bytes=len(data), object_key=key
        )
        session.add(raw)
        await session.flush()
        return raw

    async def create_batch(
        self, session: AsyncSession, store: Any, files: Sequence[tuple[str, RawRecording]]
    ) -> Batch:
        batch = Batch()
        for name, raw in files:
            batch.items.append(BatchItem(filename=name, raw_id=raw.id))
        session.add(batch)
        await session.flush()
        return batch

    async def read_raw(self, session: AsyncSession, store: Any, raw_id: int) -> bytes:
        raw = await session.get(RawRecording, raw_id)
        if raw is None or raw.expired_at is not None:
            raise expired_error()(raw_id)
        try:
            return await store.get(raw.object_key)  # type: ignore[no-any-return]
        except expired_error():
            raw.expired_at = datetime.now(UTC).replace(tzinfo=None)
            await session.flush()
            raise

    async def delete_raws_for_hash(
        self, session: AsyncSession, store: Any, content_hash: str
    ) -> int:
        rows = (
            (
                await session.execute(
                    select(RawRecording).where(RawRecording.content_hash == content_hash)
                )
            )
            .scalars()
            .all()
        )
        for raw in rows:
            await store.delete(raw.object_key)
        await session.execute(delete(RawRecording).where(RawRecording.content_hash == content_hash))
        return len(rows)

    async def upsert_enrichment(self, session: AsyncSession, session_id: int, result: Any) -> None:
        values = {
            "prompt_version": result.prompt_version,
            "model": result.model,
            "summary": result.summary,
            "category": result.category,
            "outcome": result.outcome,
            "frustration": result.frustration,
            "stuck_points": list(result.stuck_points),
            "prompt_feedback": result.prompt_feedback,
            "risk_notes": list(result.risk_notes),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        row = (
            await session.execute(select(Enrichment).where(Enrichment.session_id == session_id))
        ).scalar_one_or_none()
        if row is None:
            session.add(Enrichment(session_id=session_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await session.flush()

    async def retry_failed(self, session: AsyncSession, batch_id: int) -> None:
        await session.execute(
            update(BatchItem)
            .where(BatchItem.batch_id == batch_id, BatchItem.status == ItemStatus.failed)
            .values(status=ItemStatus.queued, error=None, attempts=0)
        )
        await session.execute(
            update(Batch).where(Batch.id == batch_id).values(status=BatchStatus.queued)
        )

    async def cancel_batch(self, session: AsyncSession, batch_id: int) -> None:
        await session.execute(
            update(BatchItem)
            .where(BatchItem.batch_id == batch_id, BatchItem.status == ItemStatus.queued)
            .values(status=ItemStatus.cancelled)
        )
        await session.execute(
            update(Batch).where(Batch.id == batch_id).values(status=BatchStatus.cancelled)
        )
