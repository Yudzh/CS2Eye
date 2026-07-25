"""Add normalized team rosters and history.

Revision ID: 0003_team_rosters
Revises: 0002_top_teams
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op


revision = "0003_team_rosters"
down_revision = "0002_top_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column(
            "roster_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bo3_id", sa.Integer(), nullable=False),
        sa.Column("bo3_slug", sa.String(160), nullable=False),
        sa.Column("nickname", sa.String(160), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("country_name", sa.String(120), nullable=True),
        sa.Column(
            "is_analytics_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bo3_id"),
    )
    op.create_index(
        op.f("ix_players_is_analytics_active"),
        "players",
        ["is_analytics_active"],
    )
    op.create_table(
        "team_participant_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("participant_type", sa.String(16), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "left_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_team_participant_memberships_team_id"),
        "team_participant_memberships",
        ["team_id"],
    )
    op.create_index(
        op.f("ix_team_participant_memberships_player_id"),
        "team_participant_memberships",
        ["player_id"],
    )
    op.create_index(
        op.f("ix_team_participant_memberships_is_active"),
        "team_participant_memberships",
        ["is_active"],
    )
    op.create_index(
        "uq_active_team_participant",
        "team_participant_memberships",
        ["team_id", "player_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_table("team_participant_memberships")
    op.drop_table("players")
    op.drop_column("teams", "roster_synced_at")
