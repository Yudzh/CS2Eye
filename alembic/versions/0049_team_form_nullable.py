"""Allow unavailable Team Form V3 scores.

Revision ID: 0049_team_form_nullable
Revises: 0048_team_form_v3_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_team_form_nullable"
down_revision = "0048_team_form_v3_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("team_form_v3_snapshots") as batch:
        batch.alter_column("form_score", existing_type=sa.Numeric(8, 4), nullable=True)
        batch.alter_column("form_delta", existing_type=sa.Numeric(8, 4), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("team_form_v3_snapshots") as batch:
        batch.alter_column("form_score", existing_type=sa.Numeric(8, 4), nullable=False)
        batch.alter_column("form_delta", existing_type=sa.Numeric(8, 4), nullable=False)
