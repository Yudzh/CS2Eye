from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.models.team import Team, TeamRoster


@pytest.fixture
async def analysis_api() -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client, factory
    await engine.dispose()


def team(team_id: int, name: str) -> Team:
    return Team(
        id=team_id, bo3_id=1000 + team_id, bo3_slug=name.lower(), name=name,
        current_rank=team_id, is_analytics_active=True,
    )


def row(
    team_id: int, map_name: str, *, level: str = "organization",
    roster_id: int | None = None, scope_key: str = "all", maps: int = 6,
    rate: float = 60,
) -> TeamMapAggregate:
    return TeamMapAggregate(
        team_id=team_id, aggregation_level=level, roster_id=roster_id,
        map_name=map_name, scope="all", scope_key=scope_key,
        maps_played=maps, maps_won=round(maps * rate / 100), maps_lost=maps - round(maps * rate / 100),
        map_win_rate=Decimal(str(rate)), rounds_played=120, rounds_won=round(120 * rate / 100),
        rounds_lost=120 - round(120 * rate / 100), round_win_rate=Decimal(str(rate)),
        ct_rounds_played=60, ct_rounds_won=round(60 * rate / 100),
        ct_rounds_lost=60 - round(60 * rate / 100), ct_win_rate=Decimal(str(rate)),
        t_rounds_played=60, t_rounds_won=round(60 * rate / 100),
        t_rounds_lost=60 - round(60 * rate / 100), t_win_rate=Decimal(str(rate)),
        overtime_maps=0, overtime_rounds_played=0, overtime_rounds_won=0,
        first_match_date=date(2026, 7, 1), last_match_date=date(2026, 8, 1),
        sample_size_score=Decimal("60"), freshness_score=Decimal("100"),
        calculated_at=datetime.now(UTC),
    )


async def seed_teams(factory, *, rosters: bool = True) -> tuple[Team, Team]:
    async with factory() as session:
        a, b = team(1, "Alpha"), team(2, "Bravo")
        session.add_all([a, b])
        await session.flush()
        if rosters:
            roster_a = TeamRoster(team_id=1, fingerprint="a" * 64, is_current=True,
                                  source="manual", resolution_status="complete")
            roster_b = TeamRoster(team_id=2, fingerprint="b" * 64, is_current=True,
                                  source="manual", resolution_status="complete")
            session.add_all([roster_a, roster_b])
            await session.flush()
            a.current_roster_id, b.current_roster_id = roster_a.id, roster_b.id
        await session.commit()
        return a, b


async def test_team_map_organization_has_strength(analysis_api) -> None:
    client, factory = analysis_api
    await seed_teams(factory)
    async with factory() as session:
        session.add(row(1, "mirage")); await session.commit()
    payload = (await client.get("/api/v1/analysis/teams/1/maps")).json()
    assert payload["maps"][0]["strength"]["status"] == "available"
    assert payload["maps"][0]["strength"]["map_strength_score"] is not None


async def test_organization_and_current_roster_are_not_mixed(analysis_api) -> None:
    client, factory = analysis_api
    a, _ = await seed_teams(factory)
    async with factory() as session:
        session.add_all([
            row(1, "mirage", rate=80),
            row(1, "mirage", level="roster", roster_id=a.current_roster_id, rate=40),
        ]); await session.commit()
    org = (await client.get("/api/v1/analysis/teams/1/maps?aggregation_level=organization")).json()
    roster = (await client.get("/api/v1/analysis/teams/1/maps?aggregation_level=current_roster")).json()
    assert org["maps"][0]["all"]["map_win_rate"] == 80
    assert roster["maps"][0]["all"]["map_win_rate"] == 40
    assert org["maps"][0]["strength"]["map_strength_score"] != roster["maps"][0]["strength"]["map_strength_score"]


async def test_team_map_detail_contains_strength(analysis_api) -> None:
    client, factory = analysis_api
    await seed_teams(factory)
    async with factory() as session:
        session.add(row(1, "mirage")); await session.commit()
    response = await client.get("/api/v1/analysis/teams/1/maps/mirage")
    assert response.status_code == 200
    assert response.json()["strength"]["confidence_level"] in {"low_confidence", "medium_confidence", "high_confidence"}


async def test_compare_unions_maps_and_marks_one_sided_data(analysis_api) -> None:
    client, factory = analysis_api
    a, b = await seed_teams(factory)
    async with factory() as session:
        session.add_all([
            row(1, "mirage", level="roster", roster_id=a.current_roster_id, rate=80),
            row(2, "mirage", level="roster", roster_id=b.current_roster_id, rate=50),
            row(1, "nuke", level="roster", roster_id=a.current_roster_id, rate=70),
        ]); await session.commit()
    payload = (await client.get("/api/v1/analysis/compare/teams/1/2/maps")).json()
    assert {item["map_name"] for item in payload["maps"]} == {"mirage", "nuke"}
    assert payload["maps"][0]["comparison_status"] == "comparable"
    nuke = next(item for item in payload["maps"] if item["map_name"] == "nuke")
    assert nuke["comparison_status"] == "team_b_no_data"
    assert nuke["advantage_team_id"] is None


async def test_compare_marks_insufficient_sample(analysis_api) -> None:
    client, factory = analysis_api
    a, b = await seed_teams(factory)
    async with factory() as session:
        session.add_all([
            row(1, "dust2", level="roster", roster_id=a.current_roster_id, maps=2),
            row(2, "dust2", level="roster", roster_id=b.current_roster_id, maps=5),
        ]); await session.commit()
    payload = (await client.get("/api/v1/analysis/compare/teams/1/2/maps")).json()
    assert payload["maps"][0]["comparison_status"] == "team_a_not_enough_data"
    assert payload["summary"]["not_comparable_maps"] == 1


async def test_compare_without_current_roster_is_safe(analysis_api) -> None:
    client, factory = analysis_api
    await seed_teams(factory, rosters=False)
    response = await client.get("/api/v1/analysis/compare/teams/1/2/maps")
    assert response.status_code == 200
    assert response.json()["status"] == "current_roster_unavailable"
    assert response.json()["maps"] == []


async def test_compare_rosters_with_no_maps_is_empty(analysis_api) -> None:
    client, factory = analysis_api
    await seed_teams(factory)
    payload = (await client.get("/api/v1/analysis/compare/teams/1/2/maps")).json()
    assert payload["status"] == "available" and payload["maps"] == []


async def test_compare_validates_ids_and_level(analysis_api) -> None:
    client, factory = analysis_api
    await seed_teams(factory)
    assert (await client.get("/api/v1/analysis/compare/teams/1/1/maps")).status_code == 400
    assert (await client.get("/api/v1/analysis/compare/teams/1/999/maps")).status_code == 404
    assert (await client.get("/api/v1/analysis/compare/teams/1/2/maps?aggregation_level=bad")).status_code == 422
