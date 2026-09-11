"""map strength v3 snapshots

Revision ID: 0046_map_strength_v3
Revises: 0045_team_form_v3
"""
from alembic import op
import sqlalchemy as sa
revision="0046_map_strength_v3";down_revision="0045_team_form_v3";branch_labels=None;depends_on=None
def upgrade():
 op.create_table("map_strength_v3_snapshots",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("team_id",sa.Integer(),sa.ForeignKey("teams.id",ondelete="CASCADE"),nullable=False),sa.Column("map_name",sa.String(160),nullable=False),sa.Column("as_of",sa.Date(),nullable=False),sa.Column("map_score",sa.Numeric(8,4),nullable=False),sa.Column("map_delta",sa.Numeric(8,4),nullable=False),sa.Column("ct_score",sa.Numeric(8,4)),sa.Column("ct_delta",sa.Numeric(8,4)),sa.Column("t_score",sa.Numeric(8,4)),sa.Column("t_delta",sa.Numeric(8,4)),sa.Column("reliability",sa.Numeric(8,4),nullable=False),sa.Column("breakdown",sa.JSON(),nullable=False),sa.Column("model_version",sa.String(32),nullable=False),sa.Column("calculated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("team_id","map_name","as_of","model_version",name="uq_map_strength_v3_snapshot"))
 op.create_index("ix_map_strength_v3_snapshots_team_id","map_strength_v3_snapshots",["team_id"]);op.create_index("ix_map_strength_v3_snapshots_map_name","map_strength_v3_snapshots",["map_name"]);op.create_index("ix_map_strength_v3_snapshots_as_of","map_strength_v3_snapshots",["as_of"])
def downgrade():op.drop_table("map_strength_v3_snapshots")
