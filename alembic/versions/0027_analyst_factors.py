"""Qualitative analyst factors.

Revision ID: 0027_analyst_factors
Revises: 0026_tournament_visual_layout
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_analyst_factors"
down_revision = "0026_tournament_visual_layout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_factors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("factor_type", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32)),
        sa.Column("map_name", sa.String(32)),
        sa.Column("environment", sa.String(16), nullable=False, server_default="any"),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("factor_type IN ('positive','negative')", name="ck_analyst_factors_type"),
        sa.CheckConstraint("environment IN ('lan','online','any')", name="ck_analyst_factors_environment"),
        sa.CheckConstraint("category IS NULL OR category IN ('overall','ct_defense','t_attack','tactics','veto','form','communication','roles','individual','teamplay','mental','coach','roster','other')", name="ck_analyst_factors_category"),
    )
    for column in ("team_id", "coach_id", "category", "map_name", "environment", "is_active"):
        op.create_index(f"ix_analyst_factors_{column}", "analyst_factors", [column])
    op.create_index("ix_analyst_factors_team_active", "analyst_factors", ["team_id", "is_active"])
    op.create_table(
        "analyst_factor_players",
        sa.Column("analyst_factor_id", sa.Integer(), sa.ForeignKey("analyst_factors.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_analyst_factor_players_player_id", "analyst_factor_players", ["player_id"])


def downgrade() -> None:
    op.drop_table("analyst_factor_players")
    op.drop_table("analyst_factors")
