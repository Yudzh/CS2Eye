"""Persist safe business-validation diagnostics for failed LLM runs."""
from alembic import op
import sqlalchemy as sa

revision = "0033_llm_validation_codes"
down_revision = "0032_match_llm_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "match_llm_analysis_runs",
        sa.Column("validation_error_codes", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_llm_analysis_runs", "validation_error_codes")
