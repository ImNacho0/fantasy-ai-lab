"""Add execution timestamps for GitHub-dispatched simulation jobs.

Revision ID: 20260810_github_dispatch
Revises: 20260810_phase4_knowledge
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_github_dispatch"
down_revision: Union[str, Sequence[str], None] = "20260810_phase5_training"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("simulation_jobs")}


def upgrade() -> None:
    columns = _columns()
    if "started_at" not in columns:
        op.add_column("simulation_jobs", sa.Column("started_at", sa.DateTime(), nullable=True))
    if "completed_at" not in columns:
        op.add_column("simulation_jobs", sa.Column("completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if "completed_at" in columns:
        op.drop_column("simulation_jobs", "completed_at")
    if "started_at" in columns:
        op.drop_column("simulation_jobs", "started_at")
