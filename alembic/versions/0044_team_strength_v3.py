"""team strength v3

Revision ID: 0044_team_strength_v3
Revises: 0043_player_strength_v3
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_team_strength_v3"
down_revision = "0043_player_strength_v3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teams", sa.Column("team_strength_v3", sa.Numeric(8, 4), nullable=True))
    op.add_column("teams", sa.Column("team_strength_v3_reliability", sa.Numeric(8, 4), nullable=True))
    op.add_column("teams", sa.Column("team_strength_v3_breakdown", sa.JSON(), nullable=True))
    op.add_column("teams", sa.Column("team_strength_v3_model_version", sa.String(32), nullable=True))
    op.add_column("teams", sa.Column("team_strength_v3_calculated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "team_strength_v3_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("score", sa.Numeric(8, 4), nullable=True),
        sa.Column("reliability", sa.Numeric(8, 4), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "as_of", "model_version", name="uq_team_strength_v3_snapshot"),
    )
    op.create_index("ix_team_strength_v3_snapshots_team_id", "team_strength_v3_snapshots", ["team_id"])
    op.create_index("ix_team_strength_v3_snapshots_as_of", "team_strength_v3_snapshots", ["as_of"])


def downgrade():
    op.drop_index("ix_team_strength_v3_snapshots_as_of", table_name="team_strength_v3_snapshots")
    op.drop_index("ix_team_strength_v3_snapshots_team_id", table_name="team_strength_v3_snapshots")
    op.drop_table("team_strength_v3_snapshots")
    for name in ("team_strength_v3_calculated_at", "team_strength_v3_model_version", "team_strength_v3_breakdown", "team_strength_v3_reliability", "team_strength_v3"):
        op.drop_column("teams", name)
