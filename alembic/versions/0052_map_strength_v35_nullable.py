"""Allow absent map scores and diagnostic deltas in Maps V3.5.

Context, component scores, status and map entity ID live in snapshot breakdown.
"""
from alembic import op
import sqlalchemy as sa
revision = "0052_map_strength_v35_nullable"
down_revision = "0051_roster_factor"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("map_strength_v3_snapshots", "map_score", existing_type=sa.Numeric(8, 4), nullable=True)
    op.alter_column("map_strength_v3_snapshots", "map_delta", existing_type=sa.Numeric(8, 4), nullable=True)


def downgrade():
    # Null observations cannot be represented by the old schema; never fabricate 50.
    op.execute("DELETE FROM map_strength_v3_snapshots WHERE map_score IS NULL OR map_delta IS NULL")
    op.alter_column("map_strength_v3_snapshots", "map_score", existing_type=sa.Numeric(8, 4), nullable=False)
    op.alter_column("map_strength_v3_snapshots", "map_delta", existing_type=sa.Numeric(8, 4), nullable=False)
