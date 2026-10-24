"""Deliver Bucharest fixtures as part of the production release."""
from alembic import op
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_2026 import apply

revision = "0057_bucharest_deployment_data"
down_revision = "0056_match_start_time"
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Tournament data may already have forecasts, results and uploaded demos.
    # Keep those records when rolling back application schema versions.
    pass
