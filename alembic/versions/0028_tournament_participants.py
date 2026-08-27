"""Add explicit tournament participants."""
from alembic import op
import sqlalchemy as sa
revision = "0028_tournament_participants"
down_revision = "0027_analyst_factors"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("tournament_teams", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False), sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False), sa.Column("seed", sa.Integer()), sa.UniqueConstraint("tournament_id", "team_id", name="uq_tournament_teams_tournament_team"))
    op.create_index("ix_tournament_teams_tournament_id", "tournament_teams", ["tournament_id"])
    op.create_index("ix_tournament_teams_team_id", "tournament_teams", ["team_id"])
def downgrade() -> None:
    op.drop_index("ix_tournament_teams_team_id", table_name="tournament_teams")
    op.drop_index("ix_tournament_teams_tournament_id", table_name="tournament_teams")
    op.drop_table("tournament_teams")
