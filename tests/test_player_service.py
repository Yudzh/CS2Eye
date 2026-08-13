from collections.abc import AsyncIterator
from decimal import Decimal
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.integrations.bo3.client import Bo3PlayerResponse
from cs2eye.models.team import Player
from cs2eye.services.player_service import calculate_player_strength, refresh_player


class FakePlayerSource:
    async def fetch_player(self, player_id: int, slug: str) -> Bo3PlayerResponse:
        return Bo3PlayerResponse(
            id=player_id, slug=slug, nickname="donk", first_name="Danil",
            last_name="Kryshkovets", country={"code": "RU", "name": "Russia"},
            image_url="https://files.bo3.gg/donk.webp", status=1,
            six_month_avg_rating="7.2367", updated_at="2026-07-25T05:07:17+00:00",
            raw_payload={},
        )


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


def test_strength_is_bounded_and_explained() -> None:
    strength, breakdown = calculate_player_strength(Decimal("7.2367"))
    assert strength == 70
    assert breakdown is not None
    assert breakdown["model_version"] == "v2.1"
    assert breakdown["factors"][0]["available"] is False
    assert breakdown["factors"][1]["key"] == "bo3_rating"
    assert calculate_player_strength(Decimal("12"))[0] == 82
    assert calculate_player_strength(None) == (None, None)


async def test_player_refresh_updates_same_row_without_duplicates(
    session: AsyncSession,
) -> None:
    player = Player(bo3_id=31349, bo3_slug="donk", nickname="donk")
    session.add(player)
    await session.commit()

    await asyncio.wait_for(
        refresh_player(session, player.id, FakePlayerSource()),  # type: ignore[arg-type]
        3,
    )
    await asyncio.wait_for(
        refresh_player(session, player.id, FakePlayerSource()),  # type: ignore[arg-type]
        3,
    )

    assert await session.scalar(select(func.count(Player.id))) == 1
    saved = (await session.execute(select(Player))).scalar_one()
    assert saved.first_name == "Danil"
    assert saved.player_strength == 70
    assert saved.strength_breakdown["model_version"] == "v2.1"
    assert saved.bo3_rating == Decimal("7.2367")
    assert saved.stats_synced_at is not None
