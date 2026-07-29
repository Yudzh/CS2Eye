"""Move CS2Eye Internal Rating v1 to the 0-10 scale."""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0009_internal_rating_v1_scale"
down_revision: str | None = "0008_demo_player_rating"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demo_player_stats",
        sa.Column("internal_rating_version", sa.String(16), nullable=False, server_default="v1"),
    )
    op.add_column(
        "players",
        sa.Column("internal_rating_version", sa.String(16), nullable=True),
    )
    # Results created with the former 0-2 formula cannot be mixed with v1.
    op.execute("DELETE FROM demo_player_stats")
    op.execute(
        "UPDATE demo_parse_runs SET status = 'pending', finished_at = NULL, "
        "error_message = NULL WHERE status = 'success'"
    )
    op.execute(
        "UPDATE players SET internal_rating = NULL, "
        "internal_rating_maps_count = 0, internal_rating_rounds_count = 0, "
        "internal_rating_version = NULL, internal_rating_updated_at = NULL"
    )
    op.alter_column("demo_player_stats", "internal_rating_version", server_default=None)


def downgrade() -> None:
    op.drop_column("players", "internal_rating_version")
    op.drop_column("demo_player_stats", "internal_rating_version")
