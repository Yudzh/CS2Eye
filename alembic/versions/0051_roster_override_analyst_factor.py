"""Link tournament roster replacements to analyst factors.

Revision ID: 0051_roster_factor
Revises: 0050_tournament_roster_overrides
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_roster_factor"
down_revision = "0050_tournament_roster_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tournament_roster_overrides", sa.Column(
        "analyst_factor_id", sa.Integer(),
        sa.ForeignKey("analyst_factors.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_tro_analyst_factor", "tournament_roster_overrides", ["analyst_factor_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tro_analyst_factor", table_name="tournament_roster_overrides")
    op.drop_column("tournament_roster_overrides", "analyst_factor_id")
