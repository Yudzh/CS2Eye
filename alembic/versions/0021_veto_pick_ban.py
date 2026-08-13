"""veto pick ban analytics

Revision ID: 0021_veto_pick_ban
Revises: 0020_utility_analytics
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_veto_pick_ban"
down_revision = "0020_utility_analytics"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("matches", sa.Column("veto_data_status", sa.String(24), nullable=False, server_default="not_available"))
    op.add_column("matches", sa.Column("veto_source", sa.String(32)))
    op.add_column("matches", sa.Column("veto_source_external_id", sa.String(255)))
    op.add_column("matches", sa.Column("veto_source_updated_at", sa.DateTime(timezone=True)))
    op.add_column("matches", sa.Column("map_pool_version", sa.String(64)))
    op.create_check_constraint("ck_matches_veto_data_status", "matches", "veto_data_status IN ('not_available','complete','partial','needs_review','invalid')")
    op.add_column("demo_files", sa.Column("map_role", sa.String(24), nullable=False, server_default="unknown"))
    op.add_column("demo_files", sa.Column("picked_by_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")))
    op.create_index("ix_demo_files_picked_by_team_id", "demo_files", ["picked_by_team_id"])
    op.create_check_constraint("ck_demo_files_map_role", "demo_files", "map_role IN ('team_pick','opponent_pick','decider','unknown')")
    op.create_table("map_pool_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version", sa.String(64), nullable=False), sa.Column("map_name", sa.String(160), nullable=False), sa.Column("active_from", sa.Date()), sa.Column("active_to", sa.Date()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("version", "map_name", name="uq_map_pool_version_map"))
    op.create_index("ix_map_pool_entries_version", "map_pool_entries", ["version"]); op.create_index("ix_map_pool_entries_map_name", "map_pool_entries", ["map_name"])
    op.create_table("match_veto_actions", sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True), sa.Column("match_series_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False), sa.Column("order_index", sa.Integer(), nullable=False), sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")), sa.Column("team_name", sa.String(160)), sa.Column("action", sa.String(16), nullable=False), sa.Column("map_name", sa.String(160), nullable=False), sa.Column("source", sa.String(32), nullable=False, server_default="manual"), sa.Column("source_external_id", sa.String(255)), sa.Column("source_updated_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("match_series_id", "order_index", name="uq_match_veto_order"), sa.CheckConstraint("action IN ('ban','pick','decider')", name="ck_match_veto_action"))
    for name, cols in (("ix_match_veto_actions_match_series_id", ["match_series_id"]), ("ix_match_veto_actions_team_id", ["team_id"]), ("ix_match_veto_actions_map_name", ["map_name"])): op.create_index(name, "match_veto_actions", cols)

def downgrade() -> None:
    op.drop_table("match_veto_actions"); op.drop_table("map_pool_entries")
    op.drop_constraint("ck_demo_files_map_role", "demo_files", type_="check"); op.drop_index("ix_demo_files_picked_by_team_id", table_name="demo_files"); op.drop_column("demo_files", "picked_by_team_id"); op.drop_column("demo_files", "map_role")
    op.drop_constraint("ck_matches_veto_data_status", "matches", type_="check")
    for col in ("map_pool_version", "veto_source_updated_at", "veto_source_external_id", "veto_source", "veto_data_status"): op.drop_column("matches", col)
