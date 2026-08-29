"""Persist deterministic explanation plans for MatchLLMAnalysis v2 runs."""

from alembic import op
import sqlalchemy as sa


revision = "0035_explanation_plan"
down_revision = "0034_llm_grounding_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "match_llm_analysis_runs",
        sa.Column("explanation_plan_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "match_llm_analysis_runs",
        sa.Column("explanation_plan_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_llm_analysis_runs", "explanation_plan_snapshot")
    op.drop_column("match_llm_analysis_runs", "explanation_plan_schema_version")
