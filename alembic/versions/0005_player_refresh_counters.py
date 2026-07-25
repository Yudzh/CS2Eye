"""Add player profile refresh counters.

Revision ID: 0005_player_refresh_counters
Revises: 0004_player_profiles
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op


revision = "0005_player_refresh_counters"
down_revision = "0004_player_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ranking_import_runs",
        sa.Column("player_profiles_updated", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ranking_import_runs",
        sa.Column("player_profiles_failed", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ranking_import_runs", "player_profiles_failed")
    op.drop_column("ranking_import_runs", "player_profiles_updated")
