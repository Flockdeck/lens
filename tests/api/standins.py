"""Minimal local stand-ins for components built in parallel (worker, recording, enrich).

Each is used only when the real module cannot be imported; once the components land, the
tests run against the real ones.
"""

import hashlib
import importlib
import json
import sys
import types
from collections.abc import Sequence
from typing import Any

import zstandard
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording


def importable(name: str) -> bool:
    try:
        importlib.import_module(name)
    except ImportError:
        return False
    return True


class FakeQueue:
    """Same signatures as worker/queue.py in docs/contracts.md, minimal behaviour."""

    async def store_raw(self, session: AsyncSession, data: bytes) -> RawRecording:
        raw = RawRecording(
            content_hash=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            data=zstandard.ZstdCompressor().compress(data),
        )
        session.add(raw)
        await session.flush()
        return raw

    async def create_batch(
        self, session: AsyncSession, files: Sequence[tuple[str, RawRecording]]
    ) -> Batch:
        batch = Batch()
        batch.items = [BatchItem(filename=n, raw_id=r.id) for n, r in files]
        session.add(batch)
        await session.flush()
        return batch

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


class StubEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    seq: int
    type: str


class StubEnrichmentError(Exception):
    def __init__(self, retryable: bool) -> None:
        super().__init__("enrichment failed")
        self.retryable = retryable


def _stub_iter_events(data: bytes, after_seq: int = 0, limit: int = 200) -> list[StubEvent]:
    events = [StubEvent(**json.loads(line)) for line in data.splitlines() if line.strip()]
    return [e for e in events if e.seq > after_seq][:limit]


def install_stubs() -> None:
    """Register stub `recording.parser` / `enrich.base` modules when the real ones are absent."""
    if not importable("session_lens.recording.parser"):
        parser: Any = types.ModuleType("session_lens.recording.parser")
        parser.iter_events = _stub_iter_events
        parser.parse = lambda data: _stub_iter_events(data, 0, 10**9)
        parser.analyze = lambda events: types.SimpleNamespace(events=len(events))
        parser.UnsupportedVersion = type("UnsupportedVersion", (Exception,), {})
        parser.EmptyRecording = type("EmptyRecording", (Exception,), {})
        sys.modules["session_lens.recording.parser"] = parser
    if not importable("session_lens.enrich.base"):
        base: Any = types.ModuleType("session_lens.enrich.base")
        base.EnrichmentError = StubEnrichmentError
        base.build_enricher = lambda settings: None
        sys.modules["session_lens.enrich.base"] = base


async def count_rows(session: AsyncSession, model: Any) -> int:
    return len((await session.execute(select(model))).scalars().all())
