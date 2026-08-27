"""Add persisted tournament prediction brackets and explicit target slots."""
from alembic import op
import sqlalchemy as sa

revision = "0029_tournament_predictions"
down_revision = "0028_tournament_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("next_match_slot", sa.String(8)))
    op.create_table("tournament_prediction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model_version", sa.String(32)), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("outdated", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_tournament_prediction_runs_tournament_id", "tournament_prediction_runs", ["tournament_id"])
    op.create_table("tournament_match_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_run_id", sa.Integer(), sa.ForeignKey("tournament_prediction_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_match_id", sa.BigInteger(), sa.ForeignKey("matches.id", ondelete="SET NULL")),
        sa.Column("round_number", sa.Integer()), sa.Column("round_label", sa.String(160)), sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("bracket_section", sa.String(16)), sa.Column("bracket_position", sa.Integer()), sa.Column("format", sa.String(16), nullable=False),
        sa.Column("team_a_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_b_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team_a_probability", sa.Numeric(10,8)), sa.Column("team_b_probability", sa.Numeric(10,8)),
        sa.Column("predicted_winner_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("confidence", sa.Numeric(8,6)), sa.Column("reliability", sa.Numeric(8,6)),
        sa.Column("prediction_type", sa.String(24), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("model_version", sa.String(32)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)))
    for name, columns in (("ix_tournament_match_predictions_prediction_run_id", ["prediction_run_id"]), ("ix_tournament_match_predictions_tournament_id", ["tournament_id"]), ("ix_tournament_match_predictions_source_match_id", ["source_match_id"])):
        op.create_index(name, "tournament_match_predictions", columns)


def downgrade() -> None:
    for name in ("ix_tournament_match_predictions_source_match_id", "ix_tournament_match_predictions_tournament_id", "ix_tournament_match_predictions_prediction_run_id"):
        op.drop_index(name, table_name="tournament_match_predictions")
    op.drop_table("tournament_match_predictions")
    op.drop_index("ix_tournament_prediction_runs_tournament_id", table_name="tournament_prediction_runs")
    op.drop_table("tournament_prediction_runs")
    op.drop_column("matches", "next_match_slot")
