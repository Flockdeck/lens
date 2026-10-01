"""Fakes behind the contract interfaces (recording.parse/analyze, Enricher)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel
from session_lens.enrich.base import EnrichmentError
from session_lens.recording.parser import EmptyRecording, UnsupportedVersion
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.db.models import Batch, BatchItem
from session_lens.storage.base import RecordingStore
from session_lens.worker.queue import create_batch


class Dump(BaseModel):
    model_config = {"extra": "allow"}


def make_analysis(session: str = "s1", **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(
        recording_session=session,
        project="proj",
        agent="claude",
        model="m",
        pane="p1",
        started_at=datetime(2026, 1, 1, 10, 0),
        ended_at=datetime(2026, 1, 1, 10, 5),
        completeness="clean",
        metrics=Dump(turns=2, tool_calls=3),
        risky_actions=[Dump(seq=4, tool="Bash", summary="rm -rf", severity="high", rule="rm")],
        files_touched=Dump(read=["a"], edited=[], commands=[]),
        warnings=["w"],
        **extra,
    )


def fake_enrichment(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        summary="did a thing",
        category="bugfix",
        outcome="done",
        frustration=0.25,
        stuck_points=[Dump(description="x", approx_seq=3)],
        prompt_feedback=None,
        risk_notes=[],
        input_tokens=100,
        output_tokens=20,
        model="mock",
        prompt_version="v1",
    )
    base.update(over)
    return SimpleNamespace(**base)


def fake_parse(data: bytes) -> list[dict[str, Any]]:
    """The fake file format is JSON lines of {"session": ..., "v": ...}; "" is empty."""
    lines = [json.loads(x) for x in data.decode().splitlines() if x.strip()]
    if not lines:
        raise EmptyRecording
    if any(line.get("v", 1) != 1 for line in lines):
        raise UnsupportedVersion("unsupported version")
    return lines


def fake_analyze(events: list[dict[str, Any]]) -> SimpleNamespace:
    return make_analysis(events[0]["session"])


def recording(session: str = "s1", v: int = 1, extra: str = "") -> bytes:
    return (json.dumps({"session": session, "v": v, "pad": extra}) + "\n").encode()


class FakeEnricher:
    """Scripted enricher: `script` is a list of exceptions/None consumed per call; after it is
    exhausted calls succeed. Tracks calls and peak concurrency."""

    def __init__(self, script: list[Exception | None] | None = None, delay: float = 0) -> None:
        self.script = list(script or [])
        self.delay = delay
        self.calls = 0
        self.active = 0
        self.peak = 0

    async def enrich(self, analysis: Any) -> SimpleNamespace:
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            step = self.script.pop(0) if self.script else None
            if step is not None:
                raise step
            return fake_enrichment()
        finally:
            self.active -= 1


def retryable(msg: str = "rate limited") -> EnrichmentError:
    return EnrichmentError(msg, retryable=True)  # type: ignore[call-arg]


def permanent(msg: str = "bad output") -> EnrichmentError:
    return EnrichmentError(msg, retryable=False)  # type: ignore[call-arg]


async def make_batch(
    sm: async_sessionmaker[AsyncSession], store: RecordingStore, files: list[tuple[str, bytes]]
) -> tuple[int, list[int]]:
    async with sm() as db:
        batch = await create_batch(db, store, files)
        await db.commit()
        items = (
            await db.execute(
                BatchItem.__table__.select()
                .where(BatchItem.batch_id == batch.id)
                .order_by(BatchItem.id)
            )
        ).all()
        return batch.id, [i.id for i in items]


async def get_item(sm: async_sessionmaker[AsyncSession], item_id: int) -> BatchItem:
    async with sm() as db:
        item = await db.get(BatchItem, item_id)
        assert item is not None
        return item


async def get_batch(sm: async_sessionmaker[AsyncSession], batch_id: int) -> Batch:
    async with sm() as db:
        batch = await db.get(Batch, batch_id)
        assert batch is not None
        return batch
