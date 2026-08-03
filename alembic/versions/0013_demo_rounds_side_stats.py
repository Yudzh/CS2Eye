"""Add demo rounds and team side aggregates."""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0013_demo_rounds_side_stats"
down_revision: str | None = "0012_demo_map_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("round_data_status", sa.String(24), nullable=False, server_default="not_parsed"))
    op.add_column("demo_map_results", sa.Column("rounds_parsed_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_demo_map_results_round_data_status", "demo_map_results", "round_data_status IN ('not_parsed','complete','partial','needs_review','invalid')")
    op.create_table(
        "demo_rounds",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("demo_file_id", sa.BigInteger(), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger()), sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("regulation_round_number", sa.Integer()), sa.Column("overtime_number", sa.Integer()), sa.Column("overtime_round_number", sa.Integer()),
        sa.Column("phase", sa.String(24), nullable=False), sa.Column("half", sa.String(32), nullable=False),
        sa.Column("team_a_side", sa.String(8), nullable=False), sa.Column("team_b_side", sa.String(8), nullable=False),
        sa.Column("winner_team_id", sa.Integer()), sa.Column("winner_team_name", sa.String(160)), sa.Column("winner_side", sa.String(8), nullable=False),
        sa.Column("end_reason", sa.String(40), nullable=False),
        sa.Column("team_a_score_before", sa.Integer()), sa.Column("team_b_score_before", sa.Integer()),
        sa.Column("team_a_score_after", sa.Integer()), sa.Column("team_b_score_after", sa.Integer()),
        sa.Column("started_at_tick", sa.BigInteger()), sa.Column("ended_at_tick", sa.BigInteger()), sa.Column("duration_seconds", sa.Numeric(12, 4)),
        sa.Column("is_warmup", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_restart", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["demo_file_id"], ["demo_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["demo_map_result_id"], ["demo_map_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["winner_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("demo_file_id", "round_number", name="uq_demo_round_file_number"),
    )
    op.create_index("ix_demo_rounds_demo_file_id", "demo_rounds", ["demo_file_id"])
    op.create_index("ix_demo_rounds_demo_map_result_id", "demo_rounds", ["demo_map_result_id"])
    columns = [
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("demo_file_id", sa.BigInteger(), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger(), nullable=False), sa.Column("team_id", sa.Integer()), sa.Column("team_name", sa.String(160), nullable=False),
    ]
    for prefix in ("ct", "t"):
        columns += [sa.Column(f"{prefix}_rounds_played", sa.Integer(), nullable=False), sa.Column(f"{prefix}_rounds_won", sa.Integer(), nullable=False), sa.Column(f"{prefix}_rounds_lost", sa.Integer(), nullable=False), sa.Column(f"{prefix}_win_rate", sa.Numeric(8, 4))]
    for prefix in ("first_half", "second_half", "overtime"):
        columns += [sa.Column(f"{prefix}_rounds_played", sa.Integer(), nullable=False), sa.Column(f"{prefix}_rounds_won", sa.Integer(), nullable=False)]
    columns += [sa.Column("total_rounds_played", sa.Integer(), nullable=False), sa.Column("total_rounds_won", sa.Integer(), nullable=False), sa.Column("total_rounds_lost", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.ForeignKeyConstraint(["demo_file_id"], ["demo_files.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["demo_map_result_id"], ["demo_map_results.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"), sa.UniqueConstraint("demo_file_id", "team_name", name="uq_demo_side_stat_file_team_name")]
    op.create_table("demo_team_side_stats", *columns)
    op.create_index("ix_demo_team_side_stats_demo_file_id", "demo_team_side_stats", ["demo_file_id"])


def downgrade() -> None:
    op.drop_table("demo_team_side_stats")
    op.drop_table("demo_rounds")
    op.drop_constraint("ck_demo_map_results_round_data_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "rounds_parsed_count")
    op.drop_column("demo_map_results", "round_data_status")
