"""SQLAlchemy 2.0 models. MySQL 8, utf8mb4. This file is the shared contract: change it only
with the db/worker owner, and in step with an Alembic migration."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # stored as naive UTC


class Base(DeclarativeBase):
    pass


class BatchStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"  # every item finished (some may have failed)
    cancelled = "cancelled"


class ItemStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"  # permanent failure, or attempts exhausted
    cancelled = "cancelled"


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (Index("ix_batches_created_at_status", "created_at", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus), default=BatchStatus.queued)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    items: Mapped[list[BatchItem]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class RawRecording(Base):
    """One uploaded file: a row here, the bytes in the object store under `object_key`.
    The app deletes the file after the retention period (cleanup);
    `expired_at` records that the file is gone."""

    __tablename__ = "raw_recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex of the bytes
    size_bytes: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(
        String(255), unique=True
    )  # recordings/YYYY/MM/<uuid>.jsonl
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class BatchItem(Base):
    __tablename__ = "batch_items"
    __table_args__ = (Index("ix_batch_items_status_not_before", "status", "not_before"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[ItemStatus] = mapped_column(Enum(ItemStatus), default=ItemStatus.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    not_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # backoff
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # claim time
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # never contains recording content
    error_retryable: Mapped[bool | None] = mapped_column(nullable=True)
    raw_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_recordings.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    batch: Mapped[Batch] = relationship(back_populates="items")


class Session(Base):
    """One row per recording session. `content_hash` is the hash of the content it was last
    computed from; a longer upload of the same session supersedes it in place."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_session: Mapped[str] = mapped_column(
        String(128), unique=True
    )  # `session` in the file
    content_hash: Mapped[str] = mapped_column(String(64))
    project: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    agent: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    pane: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # clean | truncated | cut_off | partial_agent (agent reports few events)
    completeness: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)  # see docs/contracts.md "Metrics"
    risky_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    files_touched: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # {read, edited, commands}
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_recordings.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    enrichment: Mapped[Enrichment | None] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Enrichment(Base):
    __tablename__ = "enrichments"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), unique=True
    )
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))  # "mock" for the mock enricher
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    outcome: Mapped[str] = mapped_column(String(16), index=True)  # done | abandoned | stuck
    frustration: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0
    stuck_points: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    prompt_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_notes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped[Session] = relationship(back_populates="enrichment")


class AppSetting(Base):
    """A setting changed from the UI, which overrides the environment. One row per setting.
    `value` is plain text (the Anthropic key included: the database lives on the same machine as
    the `.env` this replaces, and the API never returns it)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
