"""Add Phase 4 knowledge metadata and counterfactual evidence.

Revision ID: 20260810_phase4_knowledge
Revises: 20260810_phase3_events
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_phase4_knowledge"
down_revision: Union[str, Sequence[str], None] = "20260810_phase3_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    # Phase 2 historically called Base.metadata.create_all(), which may have
    # materialized current ORM columns on a fresh database. Keep this revision
    # safe for both that schema and databases migrated strictly by Alembic.
    knowledge_columns = _columns("knowledge_cases")
    if "dataset_name" not in knowledge_columns:
        op.add_column(
            "knowledge_cases",
            sa.Column("dataset_name", sa.String(length=100), nullable=True, server_default="simulation"),
        )
    if "strategy_name" not in knowledge_columns:
        op.add_column("knowledge_cases", sa.Column("strategy_name", sa.String(length=100), nullable=True))
    if "strategy_version" not in knowledge_columns:
        op.add_column("knowledge_cases", sa.Column("strategy_version", sa.String(length=50), nullable=True))

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("knowledge_cases")}
    if "ix_knowledge_cases_decision_unique" not in indexes:
        op.create_index(
            "ix_knowledge_cases_decision_unique",
            "knowledge_cases",
            ["decision_id"],
            unique=True,
        )

    counterfactual_columns = _columns("counterfactuals")
    if "sample_size" not in counterfactual_columns:
        op.add_column("counterfactuals", sa.Column("sample_size", sa.Integer(), nullable=True, server_default="0"))
    if "confidence" not in counterfactual_columns:
        op.add_column("counterfactuals", sa.Column("confidence", sa.Float(), nullable=True, server_default="0"))
    if "source" not in counterfactual_columns:
        op.add_column(
            "counterfactuals",
            sa.Column("source", sa.String(length=50), nullable=True, server_default="explicit_estimate"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    knowledge_columns = _columns("knowledge_cases")
    counterfactual_columns = _columns("counterfactuals")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("knowledge_cases")}

    if "source" in counterfactual_columns:
        op.drop_column("counterfactuals", "source")
    if "confidence" in counterfactual_columns:
        op.drop_column("counterfactuals", "confidence")
    if "sample_size" in counterfactual_columns:
        op.drop_column("counterfactuals", "sample_size")
    if "ix_knowledge_cases_decision_unique" in indexes:
        op.drop_index("ix_knowledge_cases_decision_unique", table_name="knowledge_cases")
    if "strategy_version" in knowledge_columns:
        op.drop_column("knowledge_cases", "strategy_version")
    if "strategy_name" in knowledge_columns:
        op.drop_column("knowledge_cases", "strategy_name")
    if "dataset_name" in knowledge_columns:
        op.drop_column("knowledge_cases", "dataset_name")
