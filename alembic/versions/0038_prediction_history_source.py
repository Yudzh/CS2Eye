"""Mark live and retrospective prediction-history snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0038_prediction_source"
down_revision = "0037_prediction_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_history_snapshots", sa.Column("source", sa.String(24), nullable=False, server_default="live"))


def downgrade() -> None:
    op.drop_column("prediction_history_snapshots", "source")
