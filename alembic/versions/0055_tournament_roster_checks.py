"""Tournament start roster captures."""
from alembic import op
import sqlalchemy as sa
revision = "0055_tournament_roster_checks"
down_revision = "0054_analyst_probability_bonus"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("team_rosters") as batch:
        batch.drop_constraint("ck_team_rosters_source", type_="check")
        batch.create_check_constraint("ck_team_rosters_source", "source IN ('team_import', 'manual', 'demo', 'migration', 'tournament')")
    op.create_table("tournament_roster_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("baseline_ids", sa.JSON(), nullable=False),
        sa.Column("roster_ids", sa.JSON()), sa.Column("added_ids", sa.JSON()), sa.Column("missing_ids", sa.JSON()),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("source", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)), sa.Column("error", sa.Text()),
        sa.UniqueConstraint("tournament_id", "team_id", name="uq_tournament_roster_check"))


def downgrade():
    op.drop_table("tournament_roster_checks")
    op.execute("UPDATE team_rosters SET source = 'team_import' WHERE source = 'tournament'")
    with op.batch_alter_table("team_rosters") as batch:
        batch.drop_constraint("ck_team_rosters_source", type_="check")
        batch.create_check_constraint("ck_team_rosters_source", "source IN ('team_import', 'manual', 'demo', 'migration')")
