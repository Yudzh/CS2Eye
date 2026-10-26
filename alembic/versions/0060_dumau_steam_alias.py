"""Link dumau's approved additional Steam account in existing demos."""
from alembic import op
from sqlalchemy.orm import Session

from cs2eye.deployment.player_steam_aliases import apply

revision = "0060_dumau_steam_alias"
down_revision = "0059_bucharest_round2"
branch_labels = None
depends_on = None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Preserve links that already contributed to recorded player statistics.
    pass
