"""Fill the official Bucharest Swiss round-three pairings in existing slots."""
from alembic import op
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_round3_2026 import apply

revision = "0061_bucharest_round3"
down_revision = "0060_dumau_steam_alias"
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Preserve matches and any subsequently recorded results and forecasts.
    pass
