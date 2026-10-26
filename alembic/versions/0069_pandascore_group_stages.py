"""Keep PandaScore group quarterfinals out of the playoff bracket."""
from alembic import op
from sqlalchemy.orm import Session
from cs2eye.deployment.pandascore_group_stages import apply

revision = '0069_pandascore_group_stages'
down_revision = '0068_pandascore_events'
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Restoring the incorrect stage would hide group matches again.
    pass
