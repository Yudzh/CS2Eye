"""Persist Win Probability feature diagnostic reports."""

import sqlalchemy as sa
from alembic import op

revision = "0042_ml_feature_diagnostics"
down_revision = "0041_prediction_error_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_feature_diagnostic_runs",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("model_version",sa.String(32),nullable=False),
        sa.Column("feature_schema_version",sa.String(32),nullable=False),
        sa.Column("sample_size",sa.Integer(),nullable=False),
        sa.Column("report_json",sa.JSON(),nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ml_feature_diagnostic_runs")
