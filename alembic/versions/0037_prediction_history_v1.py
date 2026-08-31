"""Prediction History V1 immutable snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0037_prediction_history"
down_revision = "0036_llm_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_history_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.BigInteger(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="SET NULL")),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("team_a_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("team_b_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("team_strength_a", sa.Numeric(10, 4), nullable=False),
        sa.Column("team_strength_b", sa.Numeric(10, 4), nullable=False),
        sa.Column("team_strength_winner_id", sa.Integer(), sa.ForeignKey("teams.id")),
        sa.Column("matchup_a", sa.Numeric(10, 4), nullable=False),
        sa.Column("matchup_b", sa.Numeric(10, 4), nullable=False),
        sa.Column("matchup_winner_id", sa.Integer(), sa.ForeignKey("teams.id")),
        sa.Column("ml_a_probability", sa.Numeric(10, 8)),
        sa.Column("ml_b_probability", sa.Numeric(10, 8)),
        sa.Column("ml_winner_id", sa.Integer(), sa.ForeignKey("teams.id")),
        sa.Column("actual_winner_id", sa.Integer(), sa.ForeignKey("teams.id")),
    )
    op.create_index("ix_prediction_history_match", "prediction_history_snapshots", ["match_id"], unique=True)
    op.create_index("ix_prediction_history_tournament", "prediction_history_snapshots", ["tournament_id"])


def downgrade() -> None:
    op.drop_index("ix_prediction_history_tournament", table_name="prediction_history_snapshots")
    op.drop_index("ix_prediction_history_match", table_name="prediction_history_snapshots")
    op.drop_table("prediction_history_snapshots")
