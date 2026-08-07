"""Add normalized tournaments and match series.

Revision ID: 0016_matches_and_tournaments
Revises: 0015_roster_analytics
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016_matches_and_tournaments"
down_revision: str | None = "0015_roster_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(32)),
        sa.Column("environment", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()),
        sa.UniqueConstraint("name", "year", name="uq_tournaments_name_year"),
        sa.CheckConstraint("environment IN ('lan','online','unknown')", name="ck_tournaments_environment"),
    )
    op.create_index("ix_tournaments_name", "tournaments", ["name"])
    op.create_index("ix_tournaments_year", "tournaments", ["year"])
    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="SET NULL")),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("team_a_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_b_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("format", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("stage", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("environment", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("is_playoff", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_elimination", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("team_a_maps_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("team_b_maps_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winner_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("resolution_status", sa.String(24), nullable=False, server_default="unresolved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("format IN ('bo1','bo3','bo5','unknown')", name="ck_matches_format"),
        sa.CheckConstraint("stage IN ('group','swiss','round_of_32','round_of_16','quarterfinal','semifinal','final','unknown')", name="ck_matches_stage"),
        sa.CheckConstraint("environment IN ('lan','online','unknown')", name="ck_matches_environment"),
        sa.CheckConstraint("status IN ('scheduled','in_progress','completed','unknown')", name="ck_matches_status"),
        sa.CheckConstraint("resolution_status IN ('resolved','needs_review','unresolved')", name="ck_matches_resolution_status"),
    )
    for column in ("tournament_id", "match_date", "team_a_id", "team_b_id"):
        op.create_index(f"ix_matches_{column}", "matches", [column])
    op.add_column("demo_files", sa.Column("match_id", sa.BigInteger()))
    op.add_column("demo_files", sa.Column("map_number", sa.Integer()))
    op.create_foreign_key("fk_demo_files_match", "demo_files", "matches", ["match_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_demo_files_match_id", "demo_files", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_demo_files_match_id", table_name="demo_files")
    op.drop_constraint("fk_demo_files_match", "demo_files", type_="foreignkey")
    op.drop_column("demo_files", "map_number")
    op.drop_column("demo_files", "match_id")
    op.drop_table("matches")
    op.drop_table("tournaments")
