"""Track intentional removal of parsed demo source files.

Revision ID: 0024_demo_source_cleanup
Revises: 0023_win_probability_v1
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_demo_source_cleanup"
down_revision = "0023_win_probability_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "demo_files",
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("demo_files", "source_deleted_at")
