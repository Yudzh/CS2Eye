"""add demo parse run match metadata

Revision ID: 410bd8d00609
Revises: 7cbb69a1fd55
Create Date: 2026-06-06 10:37:26.536236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '410bd8d00609'
down_revision: Union[str, Sequence[str], None] = '7cbb69a1fd55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "demo_parse_runs",
        sa.Column("map_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("team_a_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "demo_parse_runs",
        sa.Column("team_b_name", sa.String(length=255), nullable=True),
    )

    op.create_index(
        "ix_demo_parse_runs_map_name",
        "demo_parse_runs",
        ["map_name"],
        unique=False,
    )
    op.create_index(
        "ix_demo_parse_runs_team_a_name",
        "demo_parse_runs",
        ["team_a_name"],
        unique=False,
    )
    op.create_index(
        "ix_demo_parse_runs_team_b_name",
        "demo_parse_runs",
        ["team_b_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_demo_parse_runs_team_b_name", table_name="demo_parse_runs")
    op.drop_index("ix_demo_parse_runs_team_a_name", table_name="demo_parse_runs")
    op.drop_index("ix_demo_parse_runs_map_name", table_name="demo_parse_runs")

    op.drop_column("demo_parse_runs", "team_b_name")
    op.drop_column("demo_parse_runs", "team_a_name")
    op.drop_column("demo_parse_runs", "map_name")
