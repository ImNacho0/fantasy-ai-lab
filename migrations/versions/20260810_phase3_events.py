"""Add Phase 3 event metadata.

Revision ID: 20260810_phase3_events
Revises: 20260810_phase2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_phase3_events"
down_revision: Union[str, Sequence[str], None] = "20260810_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("probability", sa.Float(), nullable=True))
    op.add_column("events", sa.Column("uncertainty", sa.Float(), nullable=True))
    op.add_column("events", sa.Column("consequences", sa.JSON(), nullable=True))
    op.add_column("events", sa.Column("recovery", sa.JSON(), nullable=True))
    op.add_column("events", sa.Column("source", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "source")
    op.drop_column("events", "recovery")
    op.drop_column("events", "consequences")
    op.drop_column("events", "uncertainty")
    op.drop_column("events", "probability")
