"""Allow PandaScore-only teams and remove owner-requested Beijing event data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from cs2eye.deployment.reset_beijing_2026 import apply

revision = '0068_pandascore_events'
down_revision = '0067_techno_pandascore_identity'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('teams') as batch:
        batch.alter_column('bo3_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('bo3_slug', existing_type=sa.String(160), nullable=True)
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    raise RuntimeError('Owner-requested tournament deletion cannot be reversed; reimport from PandaScore.')
