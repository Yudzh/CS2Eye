from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Team, TeamRoster
from cs2eye.services.match_service import MatchService, MatchValidationError
from cs2eye.services.team_h2h_service import TeamH2HService


DAY = date(2026, 7, 27)


@pytest.fixture
async def match_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        a = Team(id=1, bo3_id=101, bo3_slug="a", name="Alpha", is_analytics_active=True)
        b = Team(id=2, bo3_id=102, bo3_slug="b", name="Bravo", is_analytics_active=True)
        session.add_all([a, b]); await session.flush()
        ra = TeamRoster(team_id=1, fingerprint="a" * 64, is_current=True, source="manual", resolution_status="complete")
        rb = TeamRoster(team_id=2, fingerprint="b" * 64, is_current=True, source="manual", resolution_status="complete")
        session.add_all([ra, rb]); await session.flush(); a.current_roster_id, b.current_roster_id = ra.id, rb.id
        await session.commit()
    yield factory
    await engine.dispose()


async def add_map(factory, demo_id: int, score_a: int, score_b: int, *, filename: str | None = None,
                  tournament: str = "IEM", when: date = DAY, reverse: bool = False,
                  roster_a: int | None = None, roster_b: int | None = None) -> None:
    async with factory() as session:
        demo = DemoFile(id=demo_id, tournament_name=tournament, tournament_slug=tournament.lower(), match_date=when,
            original_filename=filename or f"map-{demo_id}.dem", storage_path=f"/lan/{demo_id}.dem",
            file_size_bytes=1, sha256=f"{demo_id:064x}")
        result = DemoMapResult(demo_file_id=demo_id, map_name=("mirage", "nuke", "ancient", "dust2", "inferno")[(demo_id - 1) % 5],
            team_a_id=2 if reverse else 1, team_b_id=1 if reverse else 2,
            team_a_score=score_b if reverse else score_a, team_b_score=score_a if reverse else score_b,
            winner_team_id=1 if score_a > score_b else 2, result_source="demo_parser", metadata_status="complete",
            round_data_status="complete", went_to_overtime=False)
        session.add_all([demo, result]); await session.flush()
        if roster_a: session.add(DemoTeamRoster(demo_file_id=demo_id, demo_map_result_id=result.id, team_id=1, roster_id=roster_a, team_name_snapshot="Alpha", resolution_status="complete"))
        if roster_b: session.add(DemoTeamRoster(demo_file_id=demo_id, demo_map_result_id=result.id, team_id=2, roster_id=roster_b, team_name_snapshot="Bravo", resolution_status="complete"))
        await session.commit()


async def manual(factory, ids: list[int], fmt: str):
    async with factory() as session:
        view = await MatchService(session).create_manual(ids, format=fmt, environment="lan")
        await session.commit(); return view


@pytest.mark.parametrize("scores,fmt,expected", [([(13, 8)], "bo1", (1, 0, 1)), ([(13, 8), (13, 9)], "bo3", (2, 0, 1)), ([(13, 8), (9, 13), (13, 10)], "bo3", (2, 1, 1)), ([(13, 8), (9, 13), (13, 10), (8, 13), (13, 11)], "bo5", (3, 2, 1))])
async def test_series_results(match_db, scores, fmt, expected) -> None:
    for index, score in enumerate(scores, 1): await add_map(match_db, index, *score, reverse=index % 2 == 0)
    view = await manual(match_db, list(range(1, len(scores) + 1)), fmt)
    assert (view.match.team_a_maps_won, view.match.team_b_maps_won, view.match.winner_team_id) == expected
    assert view.match.status == "completed"
    assert [m.map_number for m in view.maps] == list(range(1, len(scores) + 1))


async def test_different_tournament_or_date_cannot_merge(match_db) -> None:
    await add_map(match_db, 1, 13, 8); await add_map(match_db, 2, 13, 8, tournament="Other")
    with pytest.raises(MatchValidationError): await manual(match_db, [1, 2], "bo3")
    await add_map(match_db, 3, 13, 8, when=date(2026, 7, 28))
    with pytest.raises(MatchValidationError): await manual(match_db, [1, 3], "bo3")


async def test_automatic_grouping_requires_strong_map_order_signal(match_db) -> None:
    await add_map(match_db, 1, 13, 8, filename="alpha-vs-bravo.dem")
    await add_map(match_db, 2, 13, 9, filename="second.dem")
    async with match_db() as session:
        view = await MatchService(session).auto_group_demo(1)
        assert view.match.resolution_status == "needs_review"
        assert view.match.winner_team_id is None


async def test_automatic_grouping_resolves_numbered_bo3(match_db) -> None:
    await add_map(match_db, 1, 13, 8, filename="alpha-vs-bravo-map1.dem")
    await add_map(match_db, 2, 13, 9, filename="alpha-vs-bravo-map2.dem")
    async with match_db() as session:
        view = await MatchService(session).auto_group_demo(1)
        assert view.match.resolution_status == "resolved" and view.match.format == "bo3"
        assert view.match.team_a_maps_won == 2


async def test_split_demo_parts_count_as_one_logical_map(match_db) -> None:
    await add_map(match_db, 1, 13, 5, filename="alpha-vs-bravo-m1-anubis-p2.dem")
    await add_map(match_db, 2, 13, 2, filename="alpha-vs-bravo-m2-inferno.dem")
    await add_map(match_db, 3, 3, 0, filename="alpha-vs-bravo-m1-anubis-p1.dem")
    async with match_db() as session:
        part_one = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == 3))).scalar_one()
        part_one.round_data_status = "partial"
        await session.commit()
    async with match_db() as session:
        service = MatchService(session)
        proposed = await service.create_manual([1, 2, 3], format="bo3", resolution_status="needs_review")
        assert [(item.demo_file_id, item.map_number) for item in proposed.maps] == [(1, 1), (2, 2)]
        fixed = await service.auto_group_demo(1)
        await session.commit()
        assert [(item.demo_file_id, item.map_number) for item in fixed.maps] == [(1, 1), (2, 2)]
        assert fixed.match.resolution_status == "resolved"
        assert (await session.get(DemoFile, 3)).match_id is None


async def test_resolved_series_rejects_duplicate_map(match_db) -> None:
    await add_map(match_db, 1, 13, 7, filename="first.dem")
    await add_map(match_db, 2, 13, 6, filename="second.dem")
    async with match_db() as session:
        second = (await session.execute(select(DemoMapResult).where(
            DemoMapResult.demo_file_id == 2,
        ))).scalar_one()
        second.map_name = "mirage"
        await session.commit()
    with pytest.raises(MatchValidationError, match="одну карту дважды"):
        await manual(match_db, [1, 2], "bo3")


async def test_auto_group_ignores_short_fragment_and_reunites_real_maps(match_db) -> None:
    await add_map(match_db, 1, 13, 7, filename="falcons-vs-astralis-map1.dem")
    await add_map(match_db, 2, 13, 11, filename="falcons-vs-astralis-map2.dem")
    await add_map(match_db, 3, 3, 0, filename="falcons-vs-astralis-fragment.dem")
    async with match_db() as session:
        results = list((await session.execute(select(DemoMapResult).order_by(
            DemoMapResult.demo_file_id,
        ))).scalars())
        results[0].map_name = results[2].map_name = "ancient"
        results[1].map_name = "dust2"
        await session.commit()
    async with match_db() as session:
        first = await MatchService(session).create_manual(
            [1, 3], format="bo3", environment="lan",
            resolution_status="needs_review",
        )
        first.match.resolution_status = "resolved"
        await MatchService(session).recalculate(first.match.id)
        await session.commit()
    second = await manual(match_db, [2], "bo3")
    async with match_db() as session:
        fixed = await MatchService(session).auto_group_demo(1)
        await session.commit()
        assert [(item.demo_file_id, item.map_name) for item in fixed.maps] == [
            (1, "ancient"), (2, "dust2"),
        ]
        assert (fixed.match.team_a_maps_won, fixed.match.team_b_maps_won) == (2, 0)
        assert (await session.get(DemoFile, 3)).match_id is None
        assert await session.get(type(second.match), second.match.id) is None


async def test_manual_reorder_and_split(match_db) -> None:
    for demo_id in (1, 2, 3): await add_map(match_db, demo_id, 13, 8)
    view = await manual(match_db, [1, 2, 3], "bo3")
    async with match_db() as session:
        service = MatchService(session)
        reordered = await service.reorder(view.match.id, [3, 1, 2])
        assert [m.demo_file_id for m in reordered.maps] == [3, 1, 2]
        split = await service.split(view.match.id, [2]); await session.commit()
        assert len(split) == 1 and split[0].match.resolution_status == "unresolved"


async def test_team_stats_and_current_roster_do_not_mix_lineups(match_db) -> None:
    async with match_db() as session:
        a, b = await session.get(Team, 1), await session.get(Team, 2)
        ra, rb = a.current_roster_id, b.current_roster_id
        old = TeamRoster(team_id=1, fingerprint="c" * 64, is_current=False, source="demo", resolution_status="complete")
        session.add(old); await session.commit(); old_ra = old.id
    await add_map(match_db, 1, 13, 8, roster_a=ra, roster_b=rb)
    await manual(match_db, [1], "bo1")
    await add_map(match_db, 2, 13, 8, roster_a=old_ra, roster_b=rb)
    await add_map(match_db, 3, 13, 9, roster_a=ra, roster_b=rb)
    await manual(match_db, [2, 3], "bo3")
    async with match_db() as session:
        service = MatchService(session)
        org = await service.team_stats(1); current = await service.team_stats(1, aggregation_level="current_roster")
        assert org.all.matches_played == 2 and org.all.matches_won == 2
        assert org.by_format["bo1"].matches_won == 1 and org.by_format["bo3"].matches_won == 1
        assert current.all.matches_played == 1


async def test_h2h_series_only_uses_resolved_matches(match_db) -> None:
    await add_map(match_db, 1, 13, 8); await manual(match_db, [1], "bo1")
    await add_map(match_db, 2, 13, 8); await add_map(match_db, 3, 9, 13)
    async with match_db() as session:
        await MatchService(session).create_manual([2, 3], format="bo3", resolution_status="needs_review"); await session.commit()
    async with match_db() as session:
        h2h = await TeamH2HService(session, today=DAY).compare(1, 2)
        assert h2h.organizations.series_played == 1
        assert h2h.organizations.team_a_series_won == 1
        assert h2h.organizations.maps_played == 3


@pytest.fixture
async def match_api(match_db):
    app = create_app()
    async def override():
        async with match_db() as session: yield session
    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client: yield client


async def test_match_api_contract(match_db, match_api) -> None:
    await add_map(match_db, 1, 13, 8)
    created = await match_api.post("/api/v1/matches", json={"demo_file_ids": [1], "format": "bo1", "stage": "final", "environment": "lan"})
    assert created.status_code == 200
    payload = created.json(); assert payload["score"] == {"team_a": 1, "team_b": 0}
    assert payload["maps"][0]["demo_file_id"] == 1
    assert (await match_api.get(f"/api/v1/matches/{payload['id']}")).status_code == 200
    assert (await match_api.get("/api/v1/matches")).json()["total"] == 1
    stats = (await match_api.get("/api/v1/analysis/teams/1/matches")).json()
    assert stats["all"]["matches_won"] == 1 and stats["by_context"]["final"]["matches_played"] == 1
