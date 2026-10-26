"""Supply verified TYLOO reference ranking for Bucharest forecasts."""
from alembic import op
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_tyloo_ranking_2026 import apply

revision = "0062_bucharest_tyloo_ranking"
down_revision = "0061_bucharest_round3"
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Preserve reference data used by authentic saved forecasts.
    pass
