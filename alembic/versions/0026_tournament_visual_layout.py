"""Tournament visual structure and match layout metadata.

Revision ID: 0026_tournament_visual_layout
Revises: 0025_premier_season_5_map_pool
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_tournament_visual_layout"
down_revision = "0025_premier_season_5_map_pool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("structure_type", sa.String(32), nullable=False, server_default="unknown"))
    op.create_check_constraint("ck_tournaments_structure_type", "tournaments", "structure_type IN ('single_elimination','double_elimination','swiss','groups','groups_playoff','mixed','unknown')")
    op.add_column("matches", sa.Column("round_number", sa.Integer()))
    op.add_column("matches", sa.Column("round_label", sa.String(160)))
    op.add_column("matches", sa.Column("group_name", sa.String(160)))
    op.add_column("matches", sa.Column("bracket_section", sa.String(16)))
    op.add_column("matches", sa.Column("bracket_position", sa.Integer()))
    op.add_column("matches", sa.Column("next_match_id", sa.BigInteger()))
    op.create_check_constraint("ck_matches_bracket_section", "matches", "bracket_section IN ('main','upper','lower','group','swiss') OR bracket_section IS NULL")
    op.create_foreign_key("fk_matches_next_match_id", "matches", "matches", ["next_match_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_matches_next_match_id", "matches", ["next_match_id"])


def downgrade() -> None:
    op.drop_index("ix_matches_next_match_id", table_name="matches")
    op.drop_constraint("fk_matches_next_match_id", "matches", type_="foreignkey")
    op.drop_constraint("ck_matches_bracket_section", "matches", type_="check")
    for column in ("next_match_id", "bracket_position", "bracket_section", "group_name", "round_label", "round_number"):
        op.drop_column("matches", column)
    op.drop_constraint("ck_tournaments_structure_type", "tournaments", type_="check")
    op.drop_column("tournaments", "structure_type")
