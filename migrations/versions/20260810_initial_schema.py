"""Extend the Phase 1 schema for agents, knowledge, and bounded workers.

Revision ID: 20260810_phase2
Revises: a91912da31e6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from fantasy_ai_lab.database.connection import Base
from fantasy_ai_lab.database import models  # noqa: F401 - register all tables

revision: str = "20260810_phase2"
down_revision: Union[str, Sequence[str], None] = "a91912da31e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("simulation_jobs", sa.Column("checkpoint", sa.JSON(), nullable=True))
    op.add_column("decisions", sa.Column("available_actions", sa.JSON(), nullable=True))
    op.add_column("decisions", sa.Column("alternative_actions", sa.JSON(), nullable=True))
    op.add_column("decisions", sa.Column("situation_id", sa.Integer(), nullable=True))
    # The legacy decisions table is kept SQLite-compatible; the ORM enforces
    # the relationship while the new knowledge tables use real foreign keys.
    # create_all is safe here because it only creates tables introduced after
    # Phase 1; existing tables are not altered by this call.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("tournaments", "evaluations", "counterfactuals", "knowledge_cases", "scenarios"):
        Base.metadata.tables[table].drop(bind, checkfirst=True)
    op.drop_column("decisions", "situation_id")
    op.drop_column("decisions", "alternative_actions")
    op.drop_column("decisions", "available_actions")
    op.drop_column("simulation_jobs", "checkpoint")
