"""utility analytics

Revision ID: 0020_utility_analytics
Revises: 0019_opening_trades_clutches
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_utility_analytics"
down_revision = "0019_opening_trades_clutches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("utility_data_status", sa.String(24), nullable=False, server_default="not_parsed"))
    op.create_check_constraint("ck_demo_map_results_utility_data_status", "demo_map_results", "utility_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')")
    op.add_column("demo_player_stats", sa.Column("utility_data", sa.JSON(), nullable=True))
    op.add_column("team_map_aggregates", sa.Column("utility_data", sa.JSON(), nullable=True))
    op.create_table("demo_utility_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tick", sa.BigInteger(), nullable=False), sa.Column("event_kind", sa.String(16), nullable=False),
        sa.Column("grenade_type", sa.String(24), nullable=False), sa.Column("raw_grenade_type", sa.String(32), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("player_identity_key", sa.String(255), nullable=False), sa.Column("player_name", sa.String(160), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")), sa.Column("team_name", sa.String(160)),
        sa.Column("side", sa.String(8)), sa.Column("target_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("target_identity_key", sa.String(255)), sa.Column("target_name", sa.String(160)), sa.Column("target_relation", sa.String(12)),
        sa.Column("damage", sa.Integer()), sa.Column("flash_duration", sa.Numeric(10, 4)),
        sa.UniqueConstraint("demo_file_id", "event_kind", "tick", "player_identity_key", "target_identity_key", "grenade_type", name="uq_demo_utility_event"))
    for name, columns in (("ix_demo_utility_events_demo_file_id", ["demo_file_id"]), ("ix_demo_utility_events_round_id", ["round_id"]),
                          ("ix_demo_utility_events_player_id", ["player_id"]), ("ix_demo_utility_events_team_id", ["team_id"]),
                          ("ix_demo_utility_events_grenade_type", ["grenade_type"]), ("ix_demo_utility_events_file_tick", ["demo_file_id", "tick"]),
                          ("ix_demo_utility_events_round_tick", ["round_id", "tick"])):
        op.create_index(name, "demo_utility_events", columns)
    op.create_table("demo_team_utility_stats",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_name", sa.String(160), nullable=False), sa.Column("utility_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("demo_file_id", "team_name", name="uq_demo_utility_file_team"))
    for name, column in (("ix_demo_team_utility_stats_demo_file_id", "demo_file_id"), ("ix_demo_team_utility_stats_demo_map_result_id", "demo_map_result_id"), ("ix_demo_team_utility_stats_team_id", "team_id")):
        op.create_index(name, "demo_team_utility_stats", [column])


def downgrade() -> None:
    op.drop_table("demo_team_utility_stats")
    op.drop_table("demo_utility_events")
    op.drop_column("team_map_aggregates", "utility_data")
    op.drop_column("demo_player_stats", "utility_data")
    op.drop_constraint("ck_demo_map_results_utility_data_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "utility_data_status")
