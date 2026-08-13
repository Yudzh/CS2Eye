"""Round Swing V1 normalized events, model artifact and inference output."""
from alembic import op
import sqlalchemy as sa

revision = "0022_round_swing_v1"
down_revision = "0021_veto_pick_ban"
branch_labels = None
depends_on = None

PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

def upgrade() -> None:
    op.add_column("demo_map_results", sa.Column("round_swing_status", sa.String(24), nullable=False, server_default="not_calculated"))
    op.create_check_constraint("ck_demo_map_results_round_swing_status", "demo_map_results", "round_swing_status IN ('not_calculated','complete','partial','model_not_trained','needs_review','invalid')")
    op.create_table("demo_damage_events",
        sa.Column("id", PK, primary_key=True), sa.Column("demo_file_id", PK, sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_id", PK, sa.ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False), sa.Column("tick", sa.BigInteger(), nullable=False),
        sa.Column("attacker_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")), sa.Column("victim_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")),
        sa.Column("attacker_identity_key", sa.String(255), nullable=False), sa.Column("victim_identity_key", sa.String(255), nullable=False),
        sa.Column("attacker_side", sa.String(8)), sa.Column("victim_side", sa.String(8)), sa.Column("health_damage", sa.Integer(), nullable=False))
    op.create_index("ix_demo_damage_events_demo_file_id", "demo_damage_events", ["demo_file_id"]); op.create_index("ix_demo_damage_events_round_tick", "demo_damage_events", ["round_id", "tick"])
    op.create_table("demo_bomb_events",
        sa.Column("id", PK, primary_key=True), sa.Column("demo_file_id", PK, sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_id", PK, sa.ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False), sa.Column("tick", sa.BigInteger(), nullable=False),
        sa.Column("event_kind", sa.String(16), nullable=False), sa.Column("bombsite", sa.String(8)), sa.UniqueConstraint("demo_file_id", "event_kind", "tick", name="uq_demo_bomb_event"))
    op.create_index("ix_demo_bomb_events_demo_file_id", "demo_bomb_events", ["demo_file_id"]); op.create_index("ix_demo_bomb_events_round_tick", "demo_bomb_events", ["round_id", "tick"])
    op.create_table("round_win_model_artifacts",
        sa.Column("id", PK, primary_key=True), sa.Column("model_version", sa.String(16), nullable=False, unique=True), sa.Column("feature_schema_version", sa.String(16), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False), sa.Column("training_matches", sa.Integer(), nullable=False), sa.Column("training_rounds", sa.Integer(), nullable=False),
        sa.Column("validation_rounds", sa.Integer(), nullable=False), sa.Column("artifact", sa.JSON(), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("normalization", sa.JSON(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("demo_round_swing_events",
        sa.Column("id", PK, primary_key=True), sa.Column("demo_file_id", PK, sa.ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_id", PK, sa.ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False), sa.Column("kill_id", PK, sa.ForeignKey("demo_kills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version", sa.String(16), nullable=False), sa.Column("state_before", sa.JSON(), nullable=False), sa.Column("state_after", sa.JSON(), nullable=False),
        sa.Column("probability_t_before", sa.Numeric(10,8), nullable=False), sa.Column("probability_t_after", sa.Numeric(10,8), nullable=False), sa.Column("event_swing", sa.Numeric(10,8), nullable=False),
        sa.Column("credited_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL")), sa.Column("credited_identity_key", sa.String(255)),
        sa.Column("attribution", sa.JSON(), nullable=False), sa.Column("contexts", sa.JSON(), nullable=False), sa.Column("confidence", sa.Numeric(8,6), nullable=False),
        sa.UniqueConstraint("kill_id", "model_version", name="uq_demo_round_swing_kill_model"))
    op.create_index("ix_demo_round_swing_player", "demo_round_swing_events", ["credited_player_id", "model_version"])

def downgrade() -> None:
    for table in ("demo_round_swing_events", "round_win_model_artifacts", "demo_bomb_events", "demo_damage_events"): op.drop_table(table)
    op.drop_constraint("ck_demo_map_results_round_swing_status", "demo_map_results", type_="check")
    op.drop_column("demo_map_results", "round_swing_status")
