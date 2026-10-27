"""Link existing parsed Mongolz demos using the team name alias."""
from alembic import op
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.deployment.mongolz_demo_links import apply

revision = "0072_mongolz_demo_links"
down_revision = "0071_thunderpick_forecast_times"
branch_labels = None
depends_on = None


async def repair(connection):
    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        await apply(session)
        await session.flush()


def upgrade():
    op.run_async(repair)


def downgrade():
    # Keep verified map links and all recorded outcomes and forecasts.
    pass
