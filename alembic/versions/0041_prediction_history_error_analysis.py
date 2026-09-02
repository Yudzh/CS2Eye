"""Store immutable Matchup factor snapshots for error analysis."""

import sqlalchemy as sa
from alembic import op

revision = "0041_prediction_error_analysis"
down_revision = "0040_prediction_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_history_snapshots", sa.Column("matchup_factors", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("prediction_history_snapshots", "matchup_factors")
