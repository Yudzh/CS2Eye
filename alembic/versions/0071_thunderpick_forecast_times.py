"""Restore missing Thunderpick kickoffs and authentic forecast timestamp."""
from alembic import op
from sqlalchemy.orm import Session
from cs2eye.deployment.thunderpick_forecast_timestamps import apply

revision = '0071_thunderpick_forecast_times'
down_revision = '0070_pandascore_history'
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Preserve verified kickoff times and the authentic original forecast.
    pass
