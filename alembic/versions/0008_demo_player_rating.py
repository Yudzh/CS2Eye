"""Add demo parsing and player internal ratings."""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0008_demo_player_rating"
down_revision: str | None = "0007_demo_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("players", sa.Column("steam_id", sa.String(32)))
    op.add_column("players", sa.Column("internal_rating", sa.Numeric(8, 4)))
    op.add_column("players", sa.Column("internal_rating_maps_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("players", sa.Column("internal_rating_rounds_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("players", sa.Column("internal_rating_updated_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_players_steam_id", "players", ["steam_id"])
    op.create_table(
        "demo_parse_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger(), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parser_name", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("demo_file_id", name="uq_demo_parse_run_file"),
    )
    op.create_table(
        "demo_player_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger(), sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parse_run_id", sa.BigInteger(), sa.ForeignKey("demo_parse_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("steam_id", sa.String(32)),
        sa.Column("identity_key", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(160), nullable=False),
        sa.Column("team_name", sa.String(160)),
        sa.Column("rounds_played", sa.Integer(), nullable=False),
        sa.Column("kills", sa.Integer(), nullable=False),
        sa.Column("deaths", sa.Integer(), nullable=False),
        sa.Column("assists", sa.Integer(), nullable=False),
        sa.Column("total_damage", sa.Integer(), nullable=False),
        sa.Column("adr", sa.Numeric(10, 4), nullable=False),
        sa.Column("kast_rounds", sa.Integer(), nullable=False),
        sa.Column("kast_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("internal_rating", sa.Numeric(8, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("demo_file_id", "steam_id", name="uq_demo_player_steam"),
        sa.UniqueConstraint("demo_file_id", "identity_key", name="uq_demo_player_identity"),
        sa.UniqueConstraint("demo_file_id", "player_id", name="uq_demo_player_linked_player"),
    )


def downgrade() -> None:
    op.drop_table("demo_player_stats")
    op.drop_table("demo_parse_runs")
    op.drop_constraint("uq_players_steam_id", "players", type_="unique")
    for name in ("internal_rating_updated_at", "internal_rating_rounds_count", "internal_rating_maps_count", "internal_rating", "steam_id"):
        op.drop_column("players", name)
