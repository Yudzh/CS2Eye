"""Ensure the Team Strength V3 snapshot table exists.

Revision ID: 0047_team_strength_snapshot_fix
Revises: 0046_map_strength_v3

The snapshot table was added to 0044 during development after some local
databases had already applied that revision.  A forward repair migration is
required because Alembic never re-runs an applied migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "0047_team_strength_snapshot_fix"
down_revision = "0046_map_strength_v3"
branch_labels = None
depends_on = None


TABLE_NAME = "team_strength_v3_snapshots"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "team_id", sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("score", sa.Numeric(8, 4), nullable=True),
        sa.Column("reliability", sa.Numeric(8, 4), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "calculated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "team_id", "as_of", "model_version",
            name="uq_team_strength_v3_snapshot",
        ),
    )
    op.create_index(
        "ix_team_strength_v3_snapshots_team_id", TABLE_NAME, ["team_id"],
    )
    op.create_index(
        "ix_team_strength_v3_snapshots_as_of", TABLE_NAME, ["as_of"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
