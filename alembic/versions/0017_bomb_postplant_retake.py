"""bomb postplant and retake analytics

Revision ID: 0017_bomb_postplant_retake
Revises: 0016_matches_and_tournaments
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_bomb_postplant_retake"
down_revision = "0016_matches_and_tournaments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("bomb_data_status", sa.String(24), nullable=False, server_default="not_parsed"))
    op.create_check_constraint("ck_demo_map_results_bomb_data_status", "demo_map_results", "bomb_data_status IN ('not_parsed','complete','partial','needs_review','invalid')")
    for name in ("bomb_planted", "bomb_defused", "bomb_exploded"):
        op.add_column("demo_rounds", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "demo_team_bomb_stats",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_name", sa.String(160), nullable=False),
        sa.Column("t_rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bomb_plants", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plant_rate", sa.Numeric(8, 4)),
        sa.Column("postplant_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("postplant_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("postplant_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("postplant_win_rate", sa.Numeric(8, 4)),
        sa.Column("retake_opportunities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retake_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retake_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retake_win_rate", sa.Numeric(8, 4)),
        sa.Column("bomb_explosions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bomb_defuses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("demo_file_id", "team_name", name="uq_demo_bomb_stat_file_team_name"),
    )
    op.create_index("ix_demo_team_bomb_stats_demo_file_id", "demo_team_bomb_stats", ["demo_file_id"])
    op.create_index("ix_demo_team_bomb_stats_demo_map_result_id", "demo_team_bomb_stats", ["demo_map_result_id"])
    op.create_index("ix_demo_team_bomb_stats_team_id", "demo_team_bomb_stats", ["team_id"])
    integer_fields = ("bomb_t_rounds_played", "bomb_plants", "postplant_rounds", "postplant_wins", "postplant_losses", "retake_opportunities", "retake_wins", "retake_losses", "bomb_explosions", "bomb_defuses")
    rate_fields = ("plant_rate", "postplant_win_rate", "retake_win_rate")
    for name in integer_fields:
        op.add_column("team_map_aggregates", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    for name in rate_fields:
        op.add_column("team_map_aggregates", sa.Column(name, sa.Numeric(8, 4)))


def downgrade() -> None:
    for name in ("retake_win_rate", "postplant_win_rate", "plant_rate", "bomb_defuses", "bomb_explosions", "retake_losses", "retake_wins", "retake_opportunities", "postplant_losses", "postplant_wins", "postplant_rounds", "bomb_plants", "bomb_t_rounds_played"):
        op.drop_column("team_map_aggregates", name)
    op.drop_table("demo_team_bomb_stats")
    for name in ("bomb_exploded", "bomb_defused", "bomb_planted"):
        op.drop_column("demo_rounds", name)
    op.drop_constraint("ck_demo_map_results_bomb_data_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "bomb_data_status")
