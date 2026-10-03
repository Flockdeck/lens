"""model fit of an analysis, and the readable pane name of a session

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("pane_name", sa.String(length=128), nullable=True))
    op.add_column("enrichments", sa.Column("model_fit", sa.String(length=16), nullable=True))
    op.add_column("enrichments", sa.Column("model_fit_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("enrichments", "model_fit_reason")
    op.drop_column("enrichments", "model_fit")
    op.drop_column("sessions", "pane_name")
