"""add demo metadata and drop player damage stats

Revision ID: a14d21a4614a
Revises: 410bd8d00609
Create Date: 2026-06-06 11:13:23.903054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a14d21a4614a'
down_revision: Union[str, Sequence[str], None] = '410bd8d00609'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "demo_parse_runs",
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("demo_file_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("tournament_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("match_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("map_number", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_demo_parse_runs_artifact_id",
        "demo_parse_runs",
        ["artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_demo_parse_runs_tournament_name",
        "demo_parse_runs",
        ["tournament_name"],
        unique=False,
    )
    op.create_index(
        "ix_demo_parse_runs_match_date",
        "demo_parse_runs",
        ["match_date"],
        unique=False,
    )

    op.drop_index(
        "ix_demo_player_damage_stats_parse_run_id",
        table_name="demo_player_damage_stats",
    )
    op.drop_table("demo_player_damage_stats")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_table(
        "demo_player_damage_stats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("parse_run_id", sa.UUID(), nullable=False),
        sa.Column("player_name", sa.String(length=255), nullable=False),
        sa.Column("team_name", sa.String(length=255), nullable=True),
        sa.Column("total_damage", sa.Integer(), nullable=False),
        sa.Column("rounds_count", sa.Integer(), nullable=False),
        sa.Column("average_damage_per_round", sa.Float(), nullable=False),
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
        "ix_demo_player_damage_stats_parse_run_id",
        "demo_player_damage_stats",
        ["parse_run_id"],
        unique=False,
    )

    op.drop_index("ix_demo_parse_runs_match_date", table_name="demo_parse_runs")
    op.drop_index("ix_demo_parse_runs_tournament_name", table_name="demo_parse_runs")
    op.drop_index("ix_demo_parse_runs_artifact_id", table_name="demo_parse_runs")

    op.drop_column("demo_parse_runs", "map_number")
    op.drop_column("demo_parse_runs", "match_date")
    op.drop_column("demo_parse_runs", "tournament_name")
    op.drop_column("demo_parse_runs", "demo_file_name")
    op.drop_column("demo_parse_runs", "artifact_id")