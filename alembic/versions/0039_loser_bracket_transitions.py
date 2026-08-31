"""Support loser transitions in double-elimination brackets."""
from alembic import op
import sqlalchemy as sa

revision = "0039_loser_transitions"
down_revision = "0038_prediction_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("loser_next_match_id", sa.BigInteger(), sa.ForeignKey("matches.id", ondelete="SET NULL")))
    op.add_column("matches", sa.Column("loser_next_match_slot", sa.String(8)))
    op.create_index("ix_matches_loser_next_match_id", "matches", ["loser_next_match_id"])


def downgrade() -> None:
    op.drop_index("ix_matches_loser_next_match_id", table_name="matches")
    op.drop_column("matches", "loser_next_match_slot")
    op.drop_column("matches", "loser_next_match_id")
