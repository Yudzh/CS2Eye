"""PandaScore team identities and profile provenance."""
from alembic import op
import sqlalchemy as sa

revision = '0064_pandascore_teams'
down_revision = '0063_pandascore_results'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('teams', sa.Column('pandascore_id', sa.Integer(), nullable=True))
    op.create_index('uq_teams_pandascore_id', 'teams', ['pandascore_id'], unique=True)
    op.add_column('teams', sa.Column('pandascore_slug', sa.String(160), nullable=True))
    op.add_column('teams', sa.Column('pandascore_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('teams', sa.Column('pandascore_data', sa.JSON(), nullable=True))


def downgrade():
    op.drop_index('uq_teams_pandascore_id', table_name='teams')
    for column in ['pandascore_data', 'pandascore_synced_at', 'pandascore_slug', 'pandascore_id']:
        op.drop_column('teams', column)
