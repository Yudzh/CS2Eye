"""opening trades and clutches analytics

Revision ID: 0019_opening_trades_clutches
Revises: 0018_economy_and_pistols
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_opening_trades_clutches"
down_revision = "0018_economy_and_pistols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("combat_data_status", sa.String(24), nullable=False, server_default="not_parsed"))
    op.create_check_constraint("ck_demo_map_results_combat_data_status", "demo_map_results", "combat_data_status IN ('not_parsed','complete','partial','needs_review','invalid')")
    op.add_column("demo_player_stats", sa.Column("combat_data", sa.JSON()))
    op.add_column("team_map_aggregates", sa.Column("combat_data", sa.JSON()))
    op.create_table(
        "demo_team_combat_stats",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_name", sa.String(160), nullable=False), sa.Column("combat_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("demo_file_id", "team_name", name="uq_demo_combat_file_team"),
    )
    for name in ("demo_file_id", "demo_map_result_id", "team_id"):
        op.create_index(f"ix_demo_team_combat_stats_{name}", "demo_team_combat_stats", [name])
    op.create_table(
        "demo_kills",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tick", sa.BigInteger(), nullable=False),
        sa.Column("attacker_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("victim_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("assister_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("attacker_identity_key", sa.String(255)), sa.Column("victim_identity_key", sa.String(255), nullable=False), sa.Column("assister_identity_key", sa.String(255)),
        sa.Column("attacker_name", sa.String(160)), sa.Column("victim_name", sa.String(160), nullable=False),
        sa.Column("attacker_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")), sa.Column("victim_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("attacker_team_name", sa.String(160)), sa.Column("victim_team_name", sa.String(160)),
        sa.Column("attacker_side", sa.String(8)), sa.Column("victim_side", sa.String(8)), sa.Column("weapon", sa.String(80)), sa.Column("is_headshot", sa.Boolean()),
        sa.Column("is_teamkill", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_suicide", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_opening_kill", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_trade_kill", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("was_traded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("demo_file_id", "round_id", "tick", "victim_identity_key", name="uq_demo_kill_event"),
    )
    for name in ("demo_file_id", "demo_map_result_id", "round_id", "attacker_player_id", "victim_player_id", "attacker_team_id", "victim_team_id"):
        op.create_index(f"ix_demo_kills_{name}", "demo_kills", [name])
    op.create_index("ix_demo_kills_file_tick", "demo_kills", ["demo_file_id", "tick"])
    op.create_index("ix_demo_kills_round_tick", "demo_kills", ["round_id", "tick"])


def downgrade() -> None:
    op.drop_table("demo_kills")
    op.drop_table("demo_team_combat_stats")
    op.drop_column("team_map_aggregates", "combat_data")
    op.drop_column("demo_player_stats", "combat_data")
    op.drop_constraint("ck_demo_map_results_combat_data_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "combat_data_status")
