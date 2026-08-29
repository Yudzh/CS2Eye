"""Add immutable, versioned Match LLM analysis runs."""
from alembic import op
import sqlalchemy as sa

revision = "0032_match_llm_runs"
down_revision = "0031_model_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_llm_analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_run_id", sa.Integer(), sa.ForeignKey("match_llm_analysis_runs.id", ondelete="SET NULL")),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("matches.id", ondelete="SET NULL")),
        sa.Column("team_a_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("team_b_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("tournament_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tournaments.id", ondelete="SET NULL")),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_mode", sa.String(20), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("llm_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("context_schema_version", sa.String(64), nullable=False),
        sa.Column("analysis_schema_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(160)),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("analysis_snapshot", sa.JSON()),
        sa.Column("provider_response_id", sa.String(255)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("schema_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("business_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("grounding_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("repair_attempted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending','completed','failed','skipped_insufficient_data')", name="ck_match_llm_analysis_run_status"),
    )
    for column in ("source_run_id", "match_id", "team_a_id", "team_b_id", "tournament_id"):
        op.create_index(f"ix_match_llm_analysis_runs_{column}", "match_llm_analysis_runs", [column])
    op.create_index("ix_match_llm_analysis_runs_latest_match", "match_llm_analysis_runs", ["match_id", "created_at"])
    op.create_index("ix_match_llm_analysis_runs_latest_pair", "match_llm_analysis_runs", ["team_a_id", "team_b_id", "analysis_mode", "created_at"])


def downgrade() -> None:
    op.drop_table("match_llm_analysis_runs")
