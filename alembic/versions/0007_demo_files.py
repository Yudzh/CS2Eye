"""Add demo file storage metadata.

Revision ID: 0007_demo_files
Revises: 0006_team_roles
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_demo_files"
down_revision: str | None = "0006_team_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_files",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tournament_name", sa.String(length=255), nullable=False),
        sa.Column("tournament_slug", sa.String(length=255), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tournament_slug", "match_date", "original_filename",
            name="uq_demo_files_tournament_date_filename",
        ),
    )


def downgrade() -> None:
    op.drop_table("demo_files")
