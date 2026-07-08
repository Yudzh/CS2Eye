"""add teams table

Revision ID: 74933407526a
Revises: f9a28738e486
Create Date: 2026-07-08 06:24:58.503705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74933407526a'
down_revision: Union[str, Sequence[str], None] = 'f9a28738e486'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("liquipedia_url", sa.Text(), nullable=True),
        sa.Column("hltv_id", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("name"),
    )

    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=True)
    op.create_index(op.f("ix_teams_hltv_id"), "teams", ["hltv_id"], unique=False)

    op.create_table(
        "players",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nickname", sa.String(length=255), nullable=False),
        sa.Column("real_name", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("liquipedia_url", sa.Text(), nullable=True),
        sa.Column("hltv_id", sa.Integer(), nullable=True),
        sa.Column("current_rating", sa.Float(), nullable=True),
        sa.Column("player_strength_score", sa.Float(), nullable=False),
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
        sa.UniqueConstraint("nickname"),
    )

    op.create_index(op.f("ix_players_nickname"), "players", ["nickname"], unique=True)
    op.create_index(op.f("ix_players_hltv_id"), "players", ["hltv_id"], unique=False)

    op.create_table(
        "team_roster_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("joined_at", sa.Date(), nullable=True),
        sa.Column("left_at", sa.Date(), nullable=True),
        sa.Column("source_name", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_confidence", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_team_roster_members_team_id"),
        "team_roster_members",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_roster_members_player_id"),
        "team_roster_members",
        ["player_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_roster_members_status"),
        "team_roster_members",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_roster_members_role"),
        "team_roster_members",
        ["role"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_roster_members_left_at"),
        "team_roster_members",
        ["left_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_roster_members_left_at"), table_name="team_roster_members")
    op.drop_index(op.f("ix_team_roster_members_role"), table_name="team_roster_members")
    op.drop_index(op.f("ix_team_roster_members_status"), table_name="team_roster_members")
    op.drop_index(op.f("ix_team_roster_members_player_id"), table_name="team_roster_members")
    op.drop_index(op.f("ix_team_roster_members_team_id"), table_name="team_roster_members")
    op.drop_table("team_roster_members")

    op.drop_index(op.f("ix_players_hltv_id"), table_name="players")
    op.drop_index(op.f("ix_players_nickname"), table_name="players")
    op.drop_table("players")

    op.drop_index(op.f("ix_teams_hltv_id"), table_name="teams")
    op.drop_index(op.f("ix_teams_name"), table_name="teams")
    op.drop_table("teams")