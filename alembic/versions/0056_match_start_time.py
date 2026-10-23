"""Exact match start time for pre-match forecast capture."""
from alembic import op
import sqlalchemy as sa
revision = "0056_match_start_time"
down_revision = "0055_tournament_roster_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("matches", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_matches_starts_at", "matches", ["starts_at"])


def downgrade():
    op.drop_index("ix_matches_starts_at", table_name="matches")
    op.drop_column("matches", "starts_at")
