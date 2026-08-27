"""Persist prediction model quality-gate and manual activation status."""
from alembic import op
import sqlalchemy as sa

revision = "0031_model_activation"
down_revision = "0030_prediction_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_win_probability_active", table_name="win_probability_model_artifacts")
    op.alter_column("win_probability_model_artifacts", "is_active", new_column_name="active")
    op.add_column("win_probability_model_artifacts", sa.Column("trained", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("win_probability_model_artifacts", sa.Column("quality_gate_passed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("win_probability_model_artifacts", sa.Column("forced_active", sa.Boolean(), nullable=False, server_default=sa.false()))
    connection = op.get_bind()
    for artifact_id, metrics in connection.execute(sa.text(
        "SELECT id, metrics FROM win_probability_model_artifacts"
    )):
        metrics = metrics or {}
        test = metrics.get("metrics", {}).get("test", {})
        baselines = [value for value in metrics.get("baselines", {}).values() if isinstance(value, dict)]
        best_log = min((float(value["log_loss"]) for value in baselines if value.get("log_loss") is not None), default=float("inf"))
        best_brier = min((float(value["brier_score"]) for value in baselines if value.get("brier_score") is not None), default=float("inf"))
        passed = float(test.get("log_loss", float("inf"))) < best_log or float(test.get("brier_score", float("inf"))) < best_brier
        connection.execute(sa.text(
            "UPDATE win_probability_model_artifacts SET quality_gate_passed = :passed WHERE id = :id"
        ), {"passed": passed, "id": artifact_id})
    op.create_index("uq_win_probability_one_active", "win_probability_model_artifacts", ["active"], unique=True, postgresql_where=sa.text("active = true"))
    op.add_column("tournament_prediction_runs", sa.Column("model_status", sa.String(24)))
    op.add_column("tournament_prediction_runs", sa.Column("quality_gate_passed", sa.Boolean()))


def downgrade() -> None:
    op.drop_column("tournament_prediction_runs", "quality_gate_passed")
    op.drop_column("tournament_prediction_runs", "model_status")
    op.drop_index("uq_win_probability_one_active", table_name="win_probability_model_artifacts")
    op.drop_column("win_probability_model_artifacts", "forced_active")
    op.drop_column("win_probability_model_artifacts", "quality_gate_passed")
    op.drop_column("win_probability_model_artifacts", "trained")
    op.alter_column("win_probability_model_artifacts", "active", new_column_name="is_active")
    op.create_index("ix_win_probability_active", "win_probability_model_artifacts", ["is_active"])
