"""Separate official pre-match history from retrospective research rows."""
from alembic import op
import sqlalchemy as sa

revision = "0040_prediction_integrity"
down_revision = "0039_loser_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE prediction_history_snapshots SET source = 'pre_match' WHERE source = 'live'")
    op.alter_column("prediction_history_snapshots", "source", server_default="pre_match")
    op.create_check_constraint(
        "ck_prediction_history_source", "prediction_history_snapshots",
        "source IN ('pre_match','retrospective')",
    )
    op.add_column("prediction_history_snapshots", sa.Column("team_strength_model_version", sa.String(64)))
    op.add_column("prediction_history_snapshots", sa.Column("matchup_model_version", sa.String(64)))
    op.add_column("prediction_history_snapshots", sa.Column("ml_model_version", sa.String(64)))
    op.add_column("prediction_history_snapshots", sa.Column("ml_feature_schema_version", sa.String(64)))


def downgrade() -> None:
    op.drop_column("prediction_history_snapshots", "ml_feature_schema_version")
    op.drop_column("prediction_history_snapshots", "ml_model_version")
    op.drop_column("prediction_history_snapshots", "matchup_model_version")
    op.drop_column("prediction_history_snapshots", "team_strength_model_version")
    op.drop_constraint("ck_prediction_history_source", "prediction_history_snapshots", type_="check")
    op.execute("UPDATE prediction_history_snapshots SET source = 'live' WHERE source = 'pre_match'")
    op.alter_column("prediction_history_snapshots", "source", server_default="live")
