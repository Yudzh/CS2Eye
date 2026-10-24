"""Track immutable AI reports delivered with a release."""
from alembic import op
import sqlalchemy as sa

revision = "0058_ai_report_imports"
down_revision = "0057_bucharest_deployment_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_report_imports",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("source_origin", sa.String(36), nullable=False),
        sa.Column("source_run_id", sa.Integer(), nullable=False),
        sa.Column("report_run_id", sa.Integer(), sa.ForeignKey("match_llm_analysis_runs.id"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_origin", "source_run_id", name="uq_ai_report_source"))


def downgrade():
    op.drop_table("ai_report_imports")
