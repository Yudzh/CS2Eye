"""Allow a team to use a tournament-specific display name."""
from alembic import op
import sqlalchemy as sa

revision = "0053_tournament_team_name"
down_revision = "0052_map_strength_v35_nullable"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tournament_teams", sa.Column("display_name", sa.String(160), nullable=True))


def downgrade():
    op.drop_column("tournament_teams", "display_name")
