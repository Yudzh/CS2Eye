"""Fill official Bucharest Swiss round-two pairings in existing match slots."""
from alembic import op
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_round2_2026 import apply

revision = '0059_bucharest_round2'
down_revision = '0058_ai_report_imports'
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # These matches can already have uploaded demos, results and forecasts.
    pass
