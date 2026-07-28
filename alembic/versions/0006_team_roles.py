"""Add team participant roles.

Revision ID: 0006_team_roles
Revises: 0005_player_refresh_counters
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_team_roles"
down_revision: str | None = "0005_player_refresh_counters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "team_participant_memberships",
        sa.Column("role", sa.String(length=24), nullable=True),
    )
    op.alter_column(
        "team_participant_memberships",
        "joined_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_team_participant_role",
        "team_participant_memberships",
        "role IS NULL OR role IN ('igl', 'awper', 'entry_frag', 'lurk', "
        "'anchor_support', 'rifler')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_team_participant_role",
        "team_participant_memberships",
        type_="check",
    )
    op.execute(
        "UPDATE team_participant_memberships "
        "SET joined_at = CURRENT_TIMESTAMP WHERE joined_at IS NULL"
    )
    op.alter_column(
        "team_participant_memberships",
        "joined_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("team_participant_memberships", "role")
