"""Add offline LLM text quality runs and manual reviews."""

from alembic import op
import sqlalchemy as sa


revision = "0036_llm_quality"
down_revision = "0035_explanation_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_quality_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("reasoning_config", sa.JSON(), nullable=False),
        sa.Column("explanation_plan_snapshot", sa.JSON(), nullable=False),
        sa.Column("llm_output_snapshot", sa.JSON(), nullable=True),
        sa.Column("deterministic_metrics", sa.JSON(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('completed','failed')", name="ck_llm_quality_run_status"),
    )
    op.create_index("ix_llm_quality_runs_case_id", "llm_quality_runs", ["case_id"])
    op.create_index("ix_llm_quality_runs_dataset_version", "llm_quality_runs", ["dataset_version"])
    op.create_table(
        "llm_quality_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quality_run_id", sa.Integer(), sa.ForeignKey(
            "llm_quality_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("language_quality", sa.String(16), nullable=False),
        sa.Column("clarity", sa.String(16), nullable=False),
        sa.Column("usefulness", sa.String(16), nullable=False),
        sa.Column("missing_important_point", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("incorrect_emphasis", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("too_verbose", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("too_generic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_llm_quality_reviews_quality_run_id", "llm_quality_reviews", ["quality_run_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_quality_reviews_quality_run_id", table_name="llm_quality_reviews")
    op.drop_table("llm_quality_reviews")
    op.drop_index("ix_llm_quality_runs_dataset_version", table_name="llm_quality_runs")
    op.drop_index("ix_llm_quality_runs_case_id", table_name="llm_quality_runs")
    op.drop_table("llm_quality_runs")
