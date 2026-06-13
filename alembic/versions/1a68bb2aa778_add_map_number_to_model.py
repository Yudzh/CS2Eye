"""add map_number to model

Revision ID: 1a68bb2aa778
Revises: a14d21a4614a
Create Date: 2026-06-10 15:02:21.161635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a68bb2aa778'
down_revision: Union[str, Sequence[str], None] = 'a14d21a4614a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE demo_parse_runs "
        "ADD COLUMN IF NOT EXISTS map_number INTEGER"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_demo_parse_runs_map_number "
        "ON demo_parse_runs (map_number)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_demo_parse_runs_map_number"
    )

    op.execute(
        "ALTER TABLE demo_parse_runs "
        "DROP COLUMN IF EXISTS map_number"
    )