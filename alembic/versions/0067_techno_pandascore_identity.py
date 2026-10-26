"""Link Techno/Techno4K by verified provider identities and repair false substitutions."""
from alembic import op
from sqlalchemy.orm import Session
from cs2eye.deployment.pandascore_player_identities import apply

revision='0067_techno_pandascore_identity'
down_revision='0066_pandascore_replacements'
branch_labels=None
depends_on=None


def upgrade():
    with Session(bind=op.get_bind()) as session:
        apply(session)
        session.flush()


def downgrade():
    # Identity corrections preserve archived references and must not be undone into duplicates.
    pass
