import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.team import Player, Team, TeamRoster
from cs2eye.services.team_roster_service import build_roster_fingerprint, set_current_roster


def test_fingerprint_is_order_independent() -> None:
    assert build_roster_fingerprint([1, 2, 3, 4, 5]) == build_roster_fingerprint([5, 3, 1, 4, 2])


def test_one_changed_player_changes_fingerprint() -> None:
    assert build_roster_fingerprint([1, 2, 3, 4, 5]) != build_roster_fingerprint([1, 2, 3, 4, 6])


@pytest.mark.parametrize("players", [[], [1, 2, 3, 4], [1, 2, 3, 4, 4], [1, 2, 3, 4, 5, 6]])
def test_complete_fingerprint_requires_five_unique_players(players: list[int]) -> None:
    with pytest.raises(ValueError):
        build_roster_fingerprint(players)


async def test_current_roster_can_return_to_an_older_roster() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            team = Team(bo3_id=1, bo3_slug="team", name="Team")
            players = [
                Player(bo3_id=i, bo3_slug=f"player-{i}", nickname=f"Player {i}")
                for i in range(1, 7)
            ]
            session.add_all([team, *players])
            await session.flush()
            original = await set_current_roster(session, team.id, players[:5], source="team_import")
            await session.commit()
            replacement = await set_current_roster(session, team.id, players[1:], source="team_import")
            await session.commit()
            assert replacement.id > original.id

            restored = await set_current_roster(session, team.id, players[:5], source="team_import")
            await session.commit()
            assert restored.id == original.id
            assert team.current_roster_id == original.id
            assert not replacement.is_current
            # Re-importing the same lineup must also preserve the single current roster.
            await set_current_roster(session, team.id, players[:5], source="team_import")
            await session.commit()
            current_ids = list((await session.scalars(
                select(TeamRoster.id).where(TeamRoster.team_id == team.id, TeamRoster.is_current.is_(True))
            )).all())
            assert current_ids == [original.id]
            assert len(list((await session.scalars(select(TeamRoster))).all())) == 2
    finally:
        await engine.dispose()
