"""Activate the CS2 Premier Season 5 map pool.

Revision ID: 0025_premier_season_5_map_pool
Revises: 0024_demo_source_cleanup
"""

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "0025_premier_season_5_map_pool"
down_revision = "0024_demo_source_cleanup"
branch_labels = None
depends_on = None

VERSION = "premier-season-5-2026"
MAPS = ("ancient", "anubis", "cache", "dust2", "inferno", "mirage", "nuke")


def upgrade() -> None:
    table = sa.table(
        "map_pool_entries",
        sa.column("version", sa.String()),
        sa.column("map_name", sa.String()),
        sa.column("active_from", sa.Date()),
        sa.column("active_to", sa.Date()),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(table.update().where(table.c.is_active.is_(True)).values(
        is_active=False,
        active_to=date(2026, 7, 7),
    ))
    op.bulk_insert(table, [
        {
            "version": VERSION,
            "map_name": map_name,
            "active_from": date(2026, 7, 8),
            "active_to": None,
            "is_active": True,
        }
        for map_name in MAPS
    ])


def downgrade() -> None:
    table = sa.table(
        "map_pool_entries",
        sa.column("version", sa.String()),
        sa.column("active_to", sa.Date()),
        sa.column("is_active", sa.Boolean()),
    )
    op.execute(table.delete().where(table.c.version == VERSION))
    op.execute(table.update().where(
        table.c.active_to == date(2026, 7, 7),
    ).values(is_active=True, active_to=None))
