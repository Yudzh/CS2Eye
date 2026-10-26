"""PandaScore links, result provenance, review audit and shared API budget."""
from alembic import op
import sqlalchemy as sa

revision = "0063_pandascore_results"
down_revision = "0062_bucharest_tyloo_ranking"
branch_labels = None
depends_on = None


def upgrade():
    for name, type_ in [("result_source", sa.String(32)), ("result_external_id", sa.BigInteger()),
                        ("result_received_at", sa.DateTime(timezone=True)), ("result_checked_at", sa.DateTime(timezone=True)),
                        ("result_check_status", sa.String(32)), ("result_error", sa.Text()),
                        ("result_link", sa.JSON()), ("result_proposal", sa.JSON())]:
        op.add_column("matches", sa.Column(name, type_, nullable=True))
    op.add_column("matches", sa.Column("result_manual", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_matches_result_checked_at", "matches", ["result_checked_at"])
    op.create_index("uq_matches_result_external_id", "matches", ["result_external_id"], unique=True)
    op.create_table("match_result_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.BigInteger(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.String(160), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False), sa.Column("after", sa.JSON(), nullable=False))
    op.create_index("ix_match_result_audits_match_id", "match_result_audits", ["match_id"])
    quota = op.create_table("result_sync_quota", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requests", sa.JSON(), nullable=False), sa.Column("blocked_until", sa.DateTime(timezone=True)))
    op.bulk_insert(quota, [{"id": 1, "requests": []}])


def downgrade():
    op.drop_table("result_sync_quota")
    op.drop_table("match_result_audits")
    op.drop_index("uq_matches_result_external_id", table_name="matches")
    op.drop_index("ix_matches_result_checked_at", table_name="matches")
    for name in ["result_source", "result_external_id", "result_received_at", "result_checked_at",
                 "result_check_status", "result_error", "result_link", "result_proposal", "result_manual"]:
        op.drop_column("matches", name)
