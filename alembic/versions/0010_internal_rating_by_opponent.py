"""Add opponent snapshots and rating samples by opponent rank."""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0010_internal_rating_by_opponent"
down_revision: str | None = "0009_internal_rating_v1_scale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("demo_team_id", "opponent_team_id"):
        op.add_column("demo_player_stats", sa.Column(name, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_demo_player_stats_{name}_teams", "demo_player_stats", "teams",
            [name], ["id"], ondelete="SET NULL",
        )
        op.create_index(f"ix_demo_player_stats_{name}", "demo_player_stats", [name])
    op.add_column("demo_player_stats", sa.Column("demo_team_name", sa.String(160)))
    op.add_column("demo_player_stats", sa.Column("opponent_team_name", sa.String(160)))
    op.add_column("demo_player_stats", sa.Column("opponent_rank", sa.Integer()))
    op.add_column(
        "demo_player_stats",
        sa.Column("opponent_rank_group", sa.String(24), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_demo_player_stats_player_id", "demo_player_stats", ["player_id"])
    op.create_index("ix_demo_player_stats_opponent_rank_group", "demo_player_stats", ["opponent_rank_group"])
    for name in ("top15", "top16_30"):
        op.add_column("players", sa.Column(f"internal_rating_{name}", sa.Numeric(8, 4)))
        op.add_column("players", sa.Column(f"internal_rating_{name}_maps_count", sa.Integer(), nullable=False, server_default="0"))
        op.add_column("players", sa.Column(f"internal_rating_{name}_rounds_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in ("top16_30", "top15"):
        op.drop_column("players", f"internal_rating_{name}_rounds_count")
        op.drop_column("players", f"internal_rating_{name}_maps_count")
        op.drop_column("players", f"internal_rating_{name}")
    op.drop_index("ix_demo_player_stats_opponent_rank_group", table_name="demo_player_stats")
    op.drop_index("ix_demo_player_stats_player_id", table_name="demo_player_stats")
    for name in ("opponent_rank_group", "opponent_rank", "opponent_team_name", "demo_team_name"):
        op.drop_column("demo_player_stats", name)
    for name in ("opponent_team_id", "demo_team_id"):
        op.drop_index(f"ix_demo_player_stats_{name}", table_name="demo_player_stats")
        op.drop_constraint(f"fk_demo_player_stats_{name}_teams", "demo_player_stats", type_="foreignkey")
        op.drop_column("demo_player_stats", name)
