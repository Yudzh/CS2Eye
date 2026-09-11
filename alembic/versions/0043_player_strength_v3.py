"""Add parallel Player Strength V3 fields."""
import sqlalchemy as sa
from alembic import op

revision="0043_player_strength_v3"
down_revision="0042_ml_feature_diagnostics"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("players",sa.Column("mechanical_strength_v3",sa.Numeric(8,4)))
    op.add_column("players",sa.Column("supporting_strength_v3",sa.Numeric(8,4)))
    op.add_column("players",sa.Column("player_strength_v3",sa.Numeric(8,4)))
    op.add_column("players",sa.Column("player_strength_v3_reliability",sa.Numeric(8,6)))
    op.add_column("players",sa.Column("player_strength_v3_breakdown",sa.JSON()))
    op.add_column("players",sa.Column("player_strength_v3_model_version",sa.String(32)))

def downgrade():
    for name in ("player_strength_v3_model_version","player_strength_v3_breakdown","player_strength_v3_reliability","player_strength_v3","supporting_strength_v3","mechanical_strength_v3"):
        op.drop_column("players",name)
