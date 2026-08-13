"""Win Probability V1 artifacts and prediction snapshots."""
from alembic import op
import sqlalchemy as sa
revision="0023_win_probability_v1";down_revision="0022_round_swing_v1";branch_labels=None;depends_on=None
PK=sa.BigInteger().with_variant(sa.Integer(),"sqlite")
def upgrade():
    op.create_table("win_probability_model_artifacts",sa.Column("id",PK,primary_key=True),sa.Column("model_version",sa.String(32),nullable=False),sa.Column("feature_schema_version",sa.String(32),nullable=False),sa.Column("trained_at",sa.DateTime(timezone=True),nullable=False),sa.Column("training_series",sa.Integer(),nullable=False),sa.Column("validation_series",sa.Integer(),nullable=False),sa.Column("test_series",sa.Integer(),nullable=False),sa.Column("artifact",sa.JSON(),nullable=False),sa.Column("metrics",sa.JSON(),nullable=False),sa.Column("dataset_report",sa.JSON(),nullable=False),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_index("ix_win_probability_active","win_probability_model_artifacts",["is_active"])
    op.create_table("match_predictions",sa.Column("id",PK,primary_key=True),sa.Column("series_id",PK,sa.ForeignKey("matches.id",ondelete="SET NULL"),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("as_of",sa.Date(),nullable=False),sa.Column("mode",sa.String(20),nullable=False),sa.Column("source",sa.String(24),nullable=False),sa.Column("model_version",sa.String(32),nullable=False),sa.Column("feature_schema_version",sa.String(32),nullable=False),sa.Column("team_a_id",sa.Integer(),sa.ForeignKey("teams.id"),nullable=False),sa.Column("team_b_id",sa.Integer(),sa.ForeignKey("teams.id"),nullable=False),sa.Column("team_a_probability",sa.Numeric(10,8),nullable=False),sa.Column("team_b_probability",sa.Numeric(10,8),nullable=False),sa.Column("confidence",sa.Numeric(8,6),nullable=False),sa.Column("feature_snapshot",sa.JSON(),nullable=False),sa.Column("prediction_status",sa.String(24),nullable=False),sa.UniqueConstraint("series_id","mode","model_version","as_of",name="uq_match_prediction_snapshot"))
    op.create_index("ix_match_predictions_series_id","match_predictions",["series_id"])
def downgrade():
    op.drop_index("ix_match_predictions_series_id",table_name="match_predictions")
    op.drop_table("match_predictions")
    op.drop_index("ix_win_probability_active",table_name="win_probability_model_artifacts")
    op.drop_table("win_probability_model_artifacts")
