"""Add roster analytics entities and aggregate level."""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0015_roster_analytics"
down_revision: str | None = "0014_team_map_aggregates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_rosters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active_from", sa.Date()), sa.Column("active_to", sa.Date()),
        sa.Column("active_from_source", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("source", sa.String(24), nullable=False), sa.Column("resolution_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "fingerprint", name="uq_team_roster_fingerprint"),
        sa.CheckConstraint("source IN ('team_import','manual','demo','migration')", name="ck_team_rosters_source"),
        sa.CheckConstraint("resolution_status IN ('complete','partial','needs_review','invalid')", name="ck_team_rosters_resolution_status"),
    )
    op.create_index("ix_team_rosters_team_id", "team_rosters", ["team_id"])
    op.create_index("ix_team_rosters_team_current", "team_rosters", ["team_id", "is_current"])
    op.create_index("uq_team_rosters_one_current", "team_rosters", ["team_id"], unique=True,
                    postgresql_where=sa.text("is_current"), sqlite_where=sa.text("is_current = 1"))
    op.add_column("teams", sa.Column("current_roster_id", sa.Integer()))
    op.create_foreign_key("fk_teams_current_roster", "teams", "team_rosters", ["current_roster_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_teams_current_roster_id", "teams", ["current_roster_id"])
    op.create_table(
        "team_roster_members",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("roster_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer()), sa.Column("player_name_snapshot", sa.String(160), nullable=False),
        sa.Column("player_external_id", sa.String(64)), sa.Column("role_snapshot", sa.String(24)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["roster_id"], ["team_rosters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("roster_id", "player_id", name="uq_team_roster_member_player"),
    )
    op.create_index("ix_team_roster_members_roster_id", "team_roster_members", ["roster_id"])
    op.create_index("ix_team_roster_members_player_id", "team_roster_members", ["player_id"])
    op.create_table(
        "demo_team_rosters",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("demo_file_id", sa.BigInteger(), nullable=False),
        sa.Column("demo_map_result_id", sa.BigInteger(), nullable=False), sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("roster_id", sa.Integer()), sa.Column("team_name_snapshot", sa.String(160), nullable=False),
        sa.Column("resolution_status", sa.String(32), nullable=False), sa.Column("issues", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["demo_file_id"], ["demo_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["demo_map_result_id"], ["demo_map_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roster_id"], ["team_rosters.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("demo_file_id", "team_id", name="uq_demo_team_roster_file_team"),
    )
    op.create_index("ix_demo_team_rosters_file_team", "demo_team_rosters", ["demo_file_id", "team_id"])
    op.create_index("ix_demo_team_rosters_team_roster", "demo_team_rosters", ["team_id", "roster_id"])
    op.drop_constraint("uq_team_map_aggregate_business_key", "team_map_aggregates", type_="unique")
    op.add_column("team_map_aggregates", sa.Column("aggregation_level", sa.String(24), nullable=False, server_default="organization"))
    op.add_column("team_map_aggregates", sa.Column("roster_id", sa.Integer()))
    op.create_foreign_key("fk_team_map_aggregates_roster", "team_map_aggregates", "team_rosters", ["roster_id"], ["id"], ondelete="CASCADE")
    op.create_check_constraint("ck_team_map_aggregate_level_roster", "team_map_aggregates", "(aggregation_level = 'organization' AND roster_id IS NULL) OR (aggregation_level = 'roster' AND roster_id IS NOT NULL)")
    op.create_unique_constraint("uq_team_map_aggregate_business_key", "team_map_aggregates", ["team_id", "map_name", "aggregation_level", "roster_id", "scope_key"])
    op.create_index("ix_team_map_aggregates_roster_id", "team_map_aggregates", ["roster_id"])
    op.create_index("ix_team_map_aggregates_team_roster_map_level", "team_map_aggregates", ["team_id", "roster_id", "map_name", "aggregation_level"])
    op.create_index("uq_team_map_aggregate_organization", "team_map_aggregates", ["team_id", "map_name", "scope_key"], unique=True,
                    postgresql_where=sa.text("aggregation_level = 'organization'"), sqlite_where=sa.text("aggregation_level = 'organization'"))
    op.create_index("uq_team_map_aggregate_roster", "team_map_aggregates", ["team_id", "roster_id", "map_name", "scope_key"], unique=True,
                    postgresql_where=sa.text("aggregation_level = 'roster'"), sqlite_where=sa.text("aggregation_level = 'roster'"))


def downgrade() -> None:
    op.drop_index("uq_team_map_aggregate_roster", table_name="team_map_aggregates")
    op.drop_index("uq_team_map_aggregate_organization", table_name="team_map_aggregates")
    op.drop_index("ix_team_map_aggregates_team_roster_map_level", table_name="team_map_aggregates")
    op.drop_constraint("uq_team_map_aggregate_business_key", "team_map_aggregates", type_="unique")
    op.drop_constraint("ck_team_map_aggregate_level_roster", "team_map_aggregates", type_="check")
    op.drop_constraint("fk_team_map_aggregates_roster", "team_map_aggregates", type_="foreignkey")
    op.drop_column("team_map_aggregates", "roster_id"); op.drop_column("team_map_aggregates", "aggregation_level")
    op.create_unique_constraint("uq_team_map_aggregate_business_key", "team_map_aggregates", ["team_id", "map_name", "scope_key"])
    op.drop_table("demo_team_rosters"); op.drop_table("team_roster_members")
    op.drop_index("ix_teams_current_roster_id", table_name="teams")
    op.drop_constraint("fk_teams_current_roster", "teams", type_="foreignkey")
    op.drop_column("teams", "current_roster_id")
    op.drop_index("uq_team_rosters_one_current", table_name="team_rosters")
    op.drop_table("team_rosters")
