"""Tournament-scoped temporary roster replacements.

Revision ID: 0050_tournament_roster_overrides
Revises: 0049_team_form_nullable
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_tournament_roster_overrides"
down_revision = "0049_team_form_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_roster_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_out_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("player_in_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_reference", sa.Text()),
        sa.Column("valid_from", sa.Date()), sa.Column("valid_until", sa.Date()),
        sa.Column("detected_at", sa.DateTime(timezone=True)), sa.Column("source_published_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(160)), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('CONFIRMED','DETECTED','MANUAL','REJECTED')", name="ck_tournament_roster_override_status"),
        sa.CheckConstraint("source_type IN ('AUTO','MANUAL')", name="ck_tournament_roster_override_source"),
        sa.CheckConstraint("player_out_id <> player_in_id", name="ck_tournament_roster_override_different_players"),
    )
    for name, column in (("ix_tro_tournament", "tournament_id"), ("ix_tro_team", "team_id"), ("ix_tro_active", "is_active")):
        op.create_index(name, "tournament_roster_overrides", [column])


def downgrade() -> None:
    op.drop_table("tournament_roster_overrides")
