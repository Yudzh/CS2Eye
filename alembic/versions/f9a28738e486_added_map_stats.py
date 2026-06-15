"""added map stats

Revision ID: f9a28738e486
Revises: 1a68bb2aa778
Create Date: 2026-06-13 10:37:58.135077

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a28738e486'
down_revision: Union[str, Sequence[str], None] = '1a68bb2aa778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "demo_round_stats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("parse_run_id", sa.UUID(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("winner_team_name", sa.String(length=255), nullable=True),
        sa.Column("winner_side", sa.String(length=20), nullable=True),
        sa.Column("ct_team_name", sa.String(length=255), nullable=True),
        sa.Column("t_team_name", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id"],
            ["demo_parse_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_demo_round_stats_parse_run_id"),
        "demo_round_stats",
        ["parse_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_demo_round_stats_winner_team_name"),
        "demo_round_stats",
        ["winner_team_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_demo_round_stats_ct_team_name"),
        "demo_round_stats",
        ["ct_team_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_demo_round_stats_t_team_name"),
        "demo_round_stats",
        ["t_team_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_demo_round_stats_t_team_name"),
        table_name="demo_round_stats",
    )
    op.drop_index(
        op.f("ix_demo_round_stats_ct_team_name"),
        table_name="demo_round_stats",
    )
    op.drop_index(
        op.f("ix_demo_round_stats_winner_team_name"),
        table_name="demo_round_stats",
    )
    op.drop_index(
        op.f("ix_demo_round_stats_parse_run_id"),
        table_name="demo_round_stats",
    )
    op.drop_table("demo_round_stats")
