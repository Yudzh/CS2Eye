"""Create the clean project baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-23
"""


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The first product table will arrive with the first feature."""


def downgrade() -> None:
    """The baseline has no product tables to remove."""
