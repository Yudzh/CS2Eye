"""Explicit analyst probability corrections, optionally scoped to one match."""
from alembic import op
import sqlalchemy as sa
revision = "0054_analyst_probability_bonus"
down_revision = "0053_tournament_team_name"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analyst_factors", sa.Column("probability_bonus_pp", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analyst_factors", sa.Column("match_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_analyst_factor_match", "analyst_factors", "matches", ["match_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_analyst_factors_match_id", "analyst_factors", ["match_id"])


def downgrade():
    op.drop_index("ix_analyst_factors_match_id", table_name="analyst_factors")
    op.drop_constraint("fk_analyst_factor_match", "analyst_factors", type_="foreignkey")
    op.drop_column("analyst_factors", "match_id")
    op.drop_column("analyst_factors", "probability_bonus_pp")
