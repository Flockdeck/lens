"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-01 13:55:10.099862
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "done", "cancelled", name="batchstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "raw_recordings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expired_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_raw_recordings_content_hash"), "raw_recordings", ["content_hash"], unique=False
    )
    op.create_index(
        op.f("ix_raw_recordings_created_at"), "raw_recordings", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_raw_recordings_expired_at"), "raw_recordings", ["expired_at"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recording_session", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("project", sa.String(length=128), nullable=True),
        sa.Column("agent", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("pane", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("completeness", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("risky_actions", sa.JSON(), nullable=False),
        sa.Column("files_touched", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("raw_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["raw_id"], ["raw_recordings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_session", "content_hash"),
    )
    op.create_index(op.f("ix_sessions_agent"), "sessions", ["agent"], unique=False)
    op.create_index(op.f("ix_sessions_model"), "sessions", ["model"], unique=False)
    op.create_index(op.f("ix_sessions_project"), "sessions", ["project"], unique=False)
    op.create_index(
        op.f("ix_sessions_recording_session"), "sessions", ["recording_session"], unique=False
    )
    op.create_index(op.f("ix_sessions_started_at"), "sessions", ["started_at"], unique=False)
    op.create_table(
        "batch_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "done", "failed", "cancelled", name="itemstatus"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column("raw_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_id"], ["raw_recordings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_items_batch_id"), "batch_items", ["batch_id"], unique=False)
    op.create_index(op.f("ix_batch_items_status"), "batch_items", ["status"], unique=False)
    op.create_table(
        "enrichments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("frustration", sa.Float(), nullable=False),
        sa.Column("stuck_points", sa.JSON(), nullable=False),
        sa.Column("prompt_feedback", sa.Text(), nullable=True),
        sa.Column("risk_notes", sa.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(op.f("ix_enrichments_category"), "enrichments", ["category"], unique=False)
    op.create_index(op.f("ix_enrichments_outcome"), "enrichments", ["outcome"], unique=False)


def downgrade() -> None:
    # Tables only: MySQL refuses to drop an index a foreign key still uses, and dropping the
    # table drops its indexes anyway. Reverse dependency order.
    op.drop_table("enrichments")
    op.drop_table("batch_items")
    op.drop_table("sessions")
    op.drop_table("raw_recordings")
    op.drop_table("batches")
