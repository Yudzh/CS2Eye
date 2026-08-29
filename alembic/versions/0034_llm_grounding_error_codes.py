"""Persist grounding validation error codes for failed LLM runs."""

from alembic import op
import sqlalchemy as sa


revision = "0034_llm_grounding_codes"
down_revision = "0033_llm_validation_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "match_llm_analysis_runs",
        sa.Column("grounding_error_codes", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_llm_analysis_runs", "grounding_error_codes")
