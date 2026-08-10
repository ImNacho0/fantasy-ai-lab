"""Add Phase 5 strategy lifecycle metadata.

Revision ID: 20260810_phase5_training
Revises: 20260810_phase4_knowledge
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_phase5_training"
down_revision: Union[str, Sequence[str], None] = "20260810_phase4_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("strategy_versions")}


def upgrade() -> None:
    columns = _columns()
    if "lifecycle_status" not in columns:
        op.add_column("strategy_versions", sa.Column("lifecycle_status", sa.String(length=50), nullable=True, server_default="candidate"))
    if "parent_version" not in columns:
        op.add_column("strategy_versions", sa.Column("parent_version", sa.String(length=50), nullable=True))
    if "promoted_at" not in columns:
        op.add_column("strategy_versions", sa.Column("promoted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    for name in ("promoted_at", "parent_version", "lifecycle_status"):
        if name in columns:
            op.drop_column("strategy_versions", name)
