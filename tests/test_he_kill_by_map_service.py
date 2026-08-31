from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.analytics.he_kill import is_he_grenade_weapon, normalize_kill_weapon
from cs2eye.db.base import Base
from cs2eye.models.demo import DemoKill, DemoMapResult
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry, Match
from cs2eye.models.team import Team
from cs2eye.services.he_kill_by_map_service import HEKillByMapService


AS_OF = date(2026, 8, 30)
POOL = ("ancient", "anubis", "cache", "dust2", "inferno", "mirage", "nuke")


@pytest.fixture
async def he_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Team(id=1, bo3_id=1, bo3_slug="alpha", name="Alpha"),
            Team(id=2, bo3_id=2, bo3_slug="bravo", name="Bravo"),
            Team(id=3, bo3_id=3, bo3_slug="charlie", name="Charlie"),
            *[
                MapPoolEntry(version="test", map_name=name, is_active=True)
                for name in POOL
            ],
        ])
        await session.commit()
    yield factory
    await engine.dispose()


async def add_map(
    session: AsyncSession, demo_id: int, map_name: str, played: date,
    *, match_id: int | None = None, kills: list[dict] | None = None,
) -> None:
    demo = DemoFile(
        id=demo_id, tournament_name="Cup", tournament_slug="cup", match_date=played,
        original_filename=f"{demo_id}.dem", storage_path=f"/{demo_id}.dem",
        file_size_bytes=1, sha256=f"{demo_id:064x}", match_id=match_id,
        map_role="unknown",
    )
    result = DemoMapResult(
        id=demo_id, demo_file_id=demo_id, map_name=map_name,
        team_a_id=1, team_a_name="Alpha", team_a_score=13,
        team_b_id=2, team_b_name="Bravo", team_b_score=10,
        winner_team_id=1, winner_team_name="Alpha", rounds_count=23,
        result_source="demo_parser", metadata_status="complete",
    )
    session.add_all([demo, result]); await session.flush()
    for index, values in enumerate(kills or [], 1):
        payload = dict(
            demo_file_id=demo_id, demo_map_result_id=demo_id, round_id=demo_id,
            tick=index, victim_identity_key=f"victim-{demo_id}-{index}",
            attacker_name="a", victim_name="b", attacker_team_name="Alpha",
            victim_team_name="Bravo", attacker_team_id=1, victim_team_id=2,
            weapon="hegrenade", is_teamkill=False, is_suicide=False,
            is_opening_kill=False, is_trade_kill=False, was_traded=False,
        )
        session.add(DemoKill(**{**payload, **values}))


@pytest.mark.parametrize("raw", ["hegrenade", "weapon_hegrenade", "HE Grenade", "he_grenade"])
def test_he_weapon_normalization(raw: str) -> None:
    assert is_he_grenade_weapon(raw)
    assert normalize_kill_weapon(raw) in {"hegrenade", "he_grenade"}


@pytest.mark.parametrize("overrides", [
    {"is_teamkill": True},
    {"is_suicide": True},
    {"weapon": "ak47"},
    {"victim_team_id": 1},
])
def test_invalid_he_kills_are_rejected(overrides: dict) -> None:
    payload = dict(
        weapon="hegrenade", is_teamkill=False, is_suicide=False,
        attacker_team_id=1, victim_team_id=2,
        attacker_team_name="Alpha", victim_team_name="Bravo",
    )
    assert not HEKillByMapService._valid_he_kill(type("Kill", (), {**payload, **overrides})())


async def test_all_seven_maps_sorted_and_empty_maps_use_baseline(he_db) -> None:
    async with he_db() as session:
        await add_map(session, 1, "de_ancient", AS_OF - timedelta(days=1), kills=[{}])
        await session.commit()
        rows = await HEKillByMapService(session).calculate(1, 2, as_of=AS_OF)
    assert {row["map"] for row in rows} == set(POOL)
    assert len(rows) == 7
    assert [row["probability"] for row in rows] == sorted(
        (row["probability"] for row in rows), reverse=True,
    )
    empty = next(row for row in rows if row["map"] == "nuke")
    assert empty["probability"] > 0
    assert empty["team_a_sample"] == empty["team_b_sample"] == 0
    assert empty["confidence"] == "low"


async def test_stats_are_separated_by_map_and_count_only_valid_kills(he_db) -> None:
    async with he_db() as session:
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=2), kills=[{}, {"weapon": "ak47"}])
        await add_map(session, 2, "mirage", AS_OF - timedelta(days=1), kills=[])
        await session.commit()
        stats = await HEKillByMapService(session)._stats(AS_OF, None)
    ancient = stats[(1, "ancient")]
    mirage = stats[(1, "mirage")]
    assert (ancient.maps_played, ancient.maps_with_he_kill, ancient.he_kills) == (1, 1, 1)
    assert (mirage.maps_played, mirage.maps_with_he_kill, mirage.he_kills) == (1, 0, 0)
    assert ancient.he_kills_per_map == ancient.map_he_kill_rate == 1
    assert mirage.map_he_kill_rate == 0


async def test_small_sample_is_shrunk_away_from_extremes(he_db) -> None:
    async with he_db() as session:
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=1), kills=[{}])
        await session.commit()
        rows = await HEKillByMapService(session).calculate(1, 2, as_of=AS_OF)
    ancient = next(row for row in rows if row["map"] == "ancient")
    assert 0 < ancient["probability"] < 1
    assert ancient["confidence"] == "low"


async def test_as_of_and_target_series_are_excluded(he_db) -> None:
    async with he_db() as session:
        session.add(Match(
            id=50, match_date=AS_OF - timedelta(days=1), team_a_id=1, team_b_id=2,
            format="bo1", status="completed", resolution_status="resolved",
            winner_team_id=1,
        )); await session.flush()
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=2), kills=[])
        await add_map(session, 2, "ancient", AS_OF - timedelta(days=1), match_id=50, kills=[{}])
        await add_map(session, 3, "ancient", AS_OF + timedelta(days=1), kills=[{}])
        await session.commit()
        stats = await HEKillByMapService(session)._stats(AS_OF, 50)
    assert stats[(1, "ancient")].maps_played == 1
    assert stats[(1, "ancient")].he_kills == 0


async def test_confidence_is_specific_to_each_map(he_db) -> None:
    async with he_db() as session:
        demo_id = 1
        for map_name, count in (("ancient", 4), ("mirage", 3), ("nuke", 1)):
            for offset in range(count):
                await add_map(session, demo_id, map_name, AS_OF - timedelta(days=offset + 1))
                demo_id += 1
        await session.commit()
        rows = await HEKillByMapService(session).calculate(1, 2, as_of=datetime(2026, 8, 30, tzinfo=UTC))
    confidence = {row["map"]: row["confidence"] for row in rows}
    assert confidence["ancient"] == "high"
    assert confidence["mirage"] == "medium"
    assert confidence["nuke"] == "low"


@pytest.mark.parametrize(("samples", "expected"), [
    ((0, 10), "low"), ((1, 1), "low"), ((1, 2), "medium"),
    ((3, 3), "medium"), ((3, 5), "high"), ((5, 4), "high"),
])
def test_confidence_v2_uses_two_sided_and_combined_sample(samples, expected) -> None:
    assert HEKillByMapService._confidence(*samples) == expected
