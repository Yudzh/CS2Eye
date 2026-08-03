"""Add team-level opponent context and map aggregates."""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0014_team_map_aggregates"
down_revision: str | None = "0013_demo_rounds_side_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_demo_files_match_date", "demo_files", ["match_date"])
    op.create_index("ix_demo_map_results_team_a_map", "demo_map_results", ["team_a_id", "map_name"])
    op.create_index("ix_demo_map_results_team_b_map", "demo_map_results", ["team_b_id", "map_name"])
    op.create_index("ix_demo_team_side_stats_file_team", "demo_team_side_stats", ["demo_file_id", "team_id"])
    op.create_table(
        "demo_team_opponent_context",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("demo_file_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False), sa.Column("opponent_team_id", sa.Integer()), sa.Column("opponent_team_name", sa.String(160)),
        sa.Column("opponent_rank", sa.Integer()), sa.Column("opponent_rank_group", sa.String(24), nullable=False), sa.Column("opponent_rank_source", sa.String(24), nullable=False),
        sa.Column("opponent_rank_snapshot_id", sa.Integer()), sa.Column("opponent_rank_snapshot_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["demo_file_id"], ["demo_files.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opponent_team_id"], ["teams.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["opponent_rank_snapshot_id"], ["team_ranking_snapshots.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("demo_file_id", "team_id", name="uq_demo_opponent_context_file_team"),
    )
    op.create_index("ix_demo_opponent_context_file_team", "demo_team_opponent_context", ["demo_file_id", "team_id"])
    op.create_table(
        "team_map_aggregates",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("team_id", sa.Integer(), nullable=False), sa.Column("map_name", sa.String(160), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False), sa.Column("scope_key", sa.String(40), nullable=False), sa.Column("window_size", sa.Integer()), sa.Column("opponent_rank_group", sa.String(24)),
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ("maps_played","maps_won","maps_lost","rounds_played","rounds_won","rounds_lost","ct_rounds_played","ct_rounds_won","ct_rounds_lost","t_rounds_played","t_rounds_won","t_rounds_lost","overtime_maps","overtime_rounds_played","overtime_rounds_won")],
        *[sa.Column(name, sa.Numeric(8,4)) for name in ("map_win_rate","round_win_rate","ct_win_rate","t_win_rate")],
        sa.Column("first_match_date", sa.Date()), sa.Column("last_match_date", sa.Date()), sa.Column("sample_size_score", sa.Numeric(8,4), nullable=False), sa.Column("freshness_score", sa.Numeric(8,4), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id", "map_name", "scope_key", name="uq_team_map_aggregate_business_key"),
    )
    op.create_index("ix_team_map_aggregates_team_map", "team_map_aggregates", ["team_id", "map_name"])


def downgrade() -> None:
    op.drop_table("team_map_aggregates")
    op.drop_table("demo_team_opponent_context")
    op.drop_index("ix_demo_team_side_stats_file_team", table_name="demo_team_side_stats")
    op.drop_index("ix_demo_map_results_team_b_map", table_name="demo_map_results")
    op.drop_index("ix_demo_map_results_team_a_map", table_name="demo_map_results")
    op.drop_index("ix_demo_files_match_date", table_name="demo_files")
