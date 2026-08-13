"""economy and pistol analytics

Revision ID: 0018_economy_and_pistols
Revises: 0017_bomb_postplant_retake
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_economy_and_pistols"
down_revision = "0017_bomb_postplant_retake"
branch_labels = None
depends_on = None

COUNTERS = (
    "pistol_rounds_played", "pistol_rounds_won", "first_pistol_opportunities",
    "first_pistol_wins", "second_pistol_opportunities", "second_pistol_wins",
    "both_pistols_opportunities", "both_pistols_wins",
    "pistol_conversion_opportunities", "pistol_conversions",
    "post_pistol_vs_force_rounds", "post_pistol_vs_force_wins",
    "second_round_comeback_opportunities", "second_round_comeback_wins",
    "eco_rounds", "eco_wins", "force_buy_rounds", "force_buy_wins",
    "full_buy_rounds", "full_buy_wins", "anti_eco_rounds", "anti_eco_wins",
    "full_buy_vs_full_buy_rounds", "full_buy_vs_full_buy_wins",
    "force_vs_full_buy_rounds", "force_vs_full_buy_wins", "save_rounds", "players_saved",
)


def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("economy_data_status", sa.String(24), nullable=False, server_default="not_parsed"))
    op.create_check_constraint("ck_demo_map_results_economy_data_status", "demo_map_results", "economy_data_status IN ('not_parsed','complete','partial','needs_review','invalid')")
    op.add_column("demo_rounds", sa.Column("is_pistol_round", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("demo_rounds", sa.Column("pistol_round_number", sa.Integer()))
    op.add_column("demo_rounds", sa.Column("team_a_equipment_value", sa.Integer()))
    op.add_column("demo_rounds", sa.Column("team_b_equipment_value", sa.Integer()))
    op.add_column("demo_rounds", sa.Column("team_a_economy", sa.String(16), nullable=False, server_default="unknown"))
    op.add_column("demo_rounds", sa.Column("team_b_economy", sa.String(16), nullable=False, server_default="unknown"))
    columns = [
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_name", sa.String(160), nullable=False),
        *[sa.Column(name, sa.Integer(), nullable=False, server_default="0") for name in COUNTERS],
        sa.Column("save_data_status", sa.String(24), nullable=False, server_default="not_parsed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("demo_file_id", "team_name", name="uq_demo_economy_file_team_name"),
    ]
    op.create_table("demo_team_economy_stats", *columns)
    for name in ("demo_file_id", "demo_map_result_id", "team_id"):
        op.create_index(f"ix_demo_team_economy_stats_{name}", "demo_team_economy_stats", [name])
    op.add_column("team_map_aggregates", sa.Column("economy_data", sa.JSON()))


def downgrade() -> None:
    op.drop_column("team_map_aggregates", "economy_data")
    op.drop_table("demo_team_economy_stats")
    for name in ("team_b_economy", "team_a_economy", "team_b_equipment_value", "team_a_equipment_value", "pistol_round_number", "is_pistol_round"):
        op.drop_column("demo_rounds", name)
    op.drop_constraint("ck_demo_map_results_economy_data_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "economy_data_status")
