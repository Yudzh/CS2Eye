"""Classify existing PandaScore event differences as temporary replacements."""
from alembic import op
from sqlalchemy.orm import Session
from cs2eye.deployment.pandascore_replacements import apply

revision = '0066_pandascore_replacements'
down_revision = '0065_pandascore_rosters'
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Preserve observed roster history, factors and saved forecasts.
    pass
