"""Persistent PandaScore series history cache."""
from alembic import op
import sqlalchemy as sa
revision = '0070_pandascore_history'
down_revision = '0069_pandascore_group_stages'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('teams', sa.Column('pandascore_history_data', sa.JSON(), nullable=True))

def downgrade():
    op.drop_column('teams', 'pandascore_history_data')
