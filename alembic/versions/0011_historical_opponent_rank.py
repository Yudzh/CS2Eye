"""Add historical opponent rank provenance and idempotent snapshots."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_historical_opponent_rank"
down_revision: str | None = "0010_internal_rating_by_opponent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "team_ranking_snapshots",
        sa.Column("source", sa.String(32), nullable=False, server_default="bo3"),
    )
    op.execute(sa.text("""
        DELETE FROM team_ranking_snapshots older
        USING team_ranking_snapshots newer
        WHERE older.team_id = newer.team_id
          AND older.ranking_date = newer.ranking_date
          AND older.id < newer.id
    """))
    op.drop_constraint(
        "uq_ranking_snapshot_run_team",
        "team_ranking_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ranking_snapshot_team_date_source",
        "team_ranking_snapshots",
        ["team_id", "ranking_date", "source"],
    )
    op.create_index(
        "ix_team_ranking_snapshots_team_date",
        "team_ranking_snapshots",
        ["team_id", "ranking_date"],
    )

    op.add_column(
        "demo_player_stats",
        sa.Column(
            "opponent_rank_source", sa.String(24), nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "demo_player_stats",
        sa.Column("opponent_rank_snapshot_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "demo_player_stats",
        sa.Column("opponent_rank_snapshot_date", sa.Date(), nullable=True),
    )
    op.create_foreign_key(
        "fk_demo_player_stats_rank_snapshot",
        "demo_player_stats",
        "team_ranking_snapshots",
        ["opponent_rank_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_demo_player_stats_opponent_rank_source",
        "demo_player_stats",
        ["opponent_rank_source"],
    )
    op.create_index(
        "ix_demo_player_stats_opponent_rank_snapshot_id",
        "demo_player_stats",
        ["opponent_rank_snapshot_id"],
    )
    op.create_check_constraint(
        "ck_demo_player_stats_opponent_rank_source",
        "demo_player_stats",
        "opponent_rank_source IN "
        "('historical_snapshot', 'current_fallback', 'unknown')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_demo_player_stats_opponent_rank_source",
        "demo_player_stats",
        type_="check",
    )
    op.drop_index(
        "ix_demo_player_stats_opponent_rank_snapshot_id",
        table_name="demo_player_stats",
    )
    op.drop_index(
        "ix_demo_player_stats_opponent_rank_source",
        table_name="demo_player_stats",
    )
    op.drop_constraint(
        "fk_demo_player_stats_rank_snapshot",
        "demo_player_stats",
        type_="foreignkey",
    )
    op.drop_column("demo_player_stats", "opponent_rank_snapshot_date")
    op.drop_column("demo_player_stats", "opponent_rank_snapshot_id")
    op.drop_column("demo_player_stats", "opponent_rank_source")
    op.drop_index(
        "ix_team_ranking_snapshots_team_date",
        table_name="team_ranking_snapshots",
    )
    op.drop_constraint(
        "uq_ranking_snapshot_team_date_source",
        "team_ranking_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ranking_snapshot_run_team",
        "team_ranking_snapshots",
        ["import_run_id", "team_id"],
    )
    op.drop_column("team_ranking_snapshots", "source")
