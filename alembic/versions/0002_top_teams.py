"""Add BO3 top teams and ranking history.

Revision ID: 0002_top_teams
Revises: 0001_initial
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op


revision = "0002_top_teams"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bo3_id", sa.Integer(), nullable=False),
        sa.Column(
            "bo3_slug",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column(
            "country_code",
            sa.String(length=8),
            nullable=True,
        ),
        sa.Column(
            "country_name",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "region",
            sa.String(length=24),
            nullable=True,
        ),
        sa.Column(
            "current_rank",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "current_points",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column(
            "rank_change",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "ranking_date",
            sa.Date(),
            nullable=True,
        ),
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
        sa.UniqueConstraint("bo3_slug"),
    )
    op.create_index(
        op.f("ix_teams_current_rank"),
        "teams",
        ["current_rank"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teams_is_analytics_active"),
        "teams",
        ["is_analytics_active"],
        unique=False,
    )

    op.create_table(
        "ranking_import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="bo3",
            nullable=False,
        ),
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "ranking_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "teams_received",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "teams_activated",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "teams_deactivated",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_payload",
            sa.JSON(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ranking_import_runs_status"),
        "ranking_import_runs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "team_ranking_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "import_run_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ranking_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "rank",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "points",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
        ),
        sa.Column(
            "rank_change",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "roster_payload",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["ranking_import_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_run_id",
            "team_id",
            name="uq_ranking_snapshot_run_team",
        ),
    )
    op.create_index(
        op.f(
            "ix_team_ranking_snapshots_import_run_id"
        ),
        "team_ranking_snapshots",
        ["import_run_id"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_team_ranking_snapshots_ranking_date"
        ),
        "team_ranking_snapshots",
        ["ranking_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_ranking_snapshots_team_id"),
        "team_ranking_snapshots",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_team_ranking_snapshots_team_id"),
        table_name="team_ranking_snapshots",
    )
    op.drop_index(
        op.f(
            "ix_team_ranking_snapshots_ranking_date"
        ),
        table_name="team_ranking_snapshots",
    )
    op.drop_index(
        op.f(
            "ix_team_ranking_snapshots_import_run_id"
        ),
        table_name="team_ranking_snapshots",
    )
    op.drop_table("team_ranking_snapshots")
    op.drop_index(
        op.f("ix_ranking_import_runs_status"),
        table_name="ranking_import_runs",
    )
    op.drop_table("ranking_import_runs")
    op.drop_index(
        op.f("ix_teams_is_analytics_active"),
        table_name="teams",
    )
    op.drop_index(
        op.f("ix_teams_current_rank"),
        table_name="teams",
    )
    op.drop_table("teams")
