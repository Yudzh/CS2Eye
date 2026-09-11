"""Add Team Form V3 tournament and component snapshot fields.

Revision ID: 0048_team_form_v3_fields
Revises: 0047_team_strength_snapshot_fix
"""

from alembic import op
import sqlalchemy as sa


revision = "0048_team_form_v3_fields"
down_revision = "0047_team_strength_snapshot_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team_form_v3_snapshots", sa.Column(
        "tournament_id", sa.Integer(), nullable=True))
    op.add_column("team_form_v3_snapshots", sa.Column(
        "current_tournament_delta", sa.Numeric(8, 4), nullable=True))
    op.add_column("team_form_v3_snapshots", sa.Column(
        "recent_60d_delta", sa.Numeric(8, 4), nullable=True))
    op.create_foreign_key("fk_team_form_v3_tournament", "team_form_v3_snapshots",
                          "tournaments", ["tournament_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_team_form_v3_snapshots_tournament_id",
                    "team_form_v3_snapshots", ["tournament_id"])


def downgrade() -> None:
    op.drop_index("ix_team_form_v3_snapshots_tournament_id",
                  table_name="team_form_v3_snapshots")
    op.drop_constraint("fk_team_form_v3_tournament",
                       "team_form_v3_snapshots", type_="foreignkey")
    op.drop_column("team_form_v3_snapshots", "recent_60d_delta")
    op.drop_column("team_form_v3_snapshots", "current_tournament_delta")
    op.drop_column("team_form_v3_snapshots", "tournament_id")
