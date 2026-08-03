"""Add one map result per demo file."""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0012_demo_map_results"
down_revision: str | None = "0011_historical_opponent_rank"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_map_results",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("demo_file_id", sa.BigInteger(), nullable=False),
        sa.Column("map_name", sa.String(160)),
        sa.Column("team_a_id", sa.Integer()), sa.Column("team_a_name", sa.String(160)), sa.Column("team_a_score", sa.Integer()),
        sa.Column("team_b_id", sa.Integer()), sa.Column("team_b_name", sa.String(160)), sa.Column("team_b_score", sa.Integer()),
        sa.Column("winner_team_id", sa.Integer()), sa.Column("winner_team_name", sa.String(160)),
        sa.Column("rounds_count", sa.Integer()), sa.Column("went_to_overtime", sa.Boolean()),
        sa.Column("result_source", sa.String(24), nullable=False), sa.Column("metadata_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["demo_file_id"], ["demo_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_a_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_b_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["winner_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("demo_file_id", name="uq_demo_map_results_demo_file"),
        sa.CheckConstraint("result_source IN ('demo_parser', 'manual_override', 'mixed', 'unknown')", name="ck_demo_map_results_source"),
        sa.CheckConstraint("metadata_status IN ('complete', 'partial', 'invalid', 'needs_review')", name="ck_demo_map_results_status"),
    )


def downgrade() -> None:
    op.drop_table("demo_map_results")
