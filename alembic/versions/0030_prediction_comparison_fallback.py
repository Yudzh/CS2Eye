"""Store matchup-score fallback values for tournament predictions."""
from alembic import op
import sqlalchemy as sa

revision = "0030_prediction_fallback"
down_revision = "0029_tournament_predictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tournament_match_predictions", sa.Column("team_a_score", sa.Numeric(8, 4)))
    op.add_column("tournament_match_predictions", sa.Column("team_b_score", sa.Numeric(8, 4)))
    op.add_column("tournament_match_predictions", sa.Column("prediction_basis", sa.String(24), nullable=False, server_default="win_probability"))


def downgrade() -> None:
    op.drop_column("tournament_match_predictions", "prediction_basis")
    op.drop_column("tournament_match_predictions", "team_b_score")
    op.drop_column("tournament_match_predictions", "team_a_score")
