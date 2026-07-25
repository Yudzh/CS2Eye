"""Add player profile and strength fields.

Revision ID: 0004_player_profiles
Revises: 0003_team_rosters
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op


revision = "0004_player_profiles"
down_revision = "0003_team_rosters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("first_name", sa.String(160)))
    op.add_column("players", sa.Column("last_name", sa.String(160)))
    op.add_column("players", sa.Column("bo3_rating", sa.Numeric(8, 4)))
    op.add_column("players", sa.Column("player_strength", sa.Integer()))
    op.add_column("players", sa.Column("strength_breakdown", sa.JSON()))
    op.add_column("players", sa.Column("source_updated_at", sa.DateTime(timezone=True)))
    op.add_column("players", sa.Column("stats_synced_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for column in (
        "stats_synced_at", "source_updated_at", "strength_breakdown",
        "player_strength", "bo3_rating", "last_name", "first_name",
    ):
        op.drop_column("players", column)
