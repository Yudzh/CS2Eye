from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team, TeamRoster, TeamRosterMember
from cs2eye.services.team_h2h_service import (
    H2HTeamNotFoundError, SameTeamH2HError, TeamH2HService,
)


TODAY = date(2026, 8, 7)


@pytest.fixture
async def h2h_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def seed(factory, *, current: bool = True) -> tuple[int | None, int | None]:
    async with factory() as session:
        a = Team(id=1, bo3_id=101, bo3_slug="alpha", name="Alpha", is_analytics_active=True)
        b = Team(id=2, bo3_id=102, bo3_slug="bravo", name="Bravo", is_analytics_active=True)
        session.add_all([a, b]); await session.flush()
        if not current:
            await session.commit(); return None, None
        ra = TeamRoster(team_id=1, fingerprint="a" * 64, is_current=True, source="manual", resolution_status="complete")
        rb = TeamRoster(team_id=2, fingerprint="b" * 64, is_current=True, source="manual", resolution_status="complete")
        session.add_all([ra, rb]); await session.flush()
        a.current_roster_id, b.current_roster_id = ra.id, rb.id
        await session.commit(); return ra.id, rb.id


async def add_map(
    factory, demo_id: int, when: date, score_left: int | None, score_right: int | None, *,
    left: int = 1, right: int = 2, map_name: str | None = "mirage",
    round_status: str = "complete", roster_a: int | None = None, roster_b: int | None = None,
    status_a: str = "complete", status_b: str = "complete", overtime: bool = False,
) -> None:
    async with factory() as session:
        demo = DemoFile(id=demo_id, tournament_name="Cup", tournament_slug=f"cup-{demo_id}", match_date=when,
                        original_filename=f"{demo_id}.dem", storage_path=f"/{demo_id}.dem", file_size_bytes=1, sha256=f"{demo_id:064x}")
        result = DemoMapResult(demo_file_id=demo_id, map_name=map_name, team_a_id=left, team_b_id=right,
            team_a_score=score_left, team_b_score=score_right, winner_team_id=None, went_to_overtime=overtime,
            result_source="demo_parser", metadata_status="complete", round_data_status=round_status)
        session.add_all([demo, result]); await session.flush()
        if roster_a is not None:
            session.add(DemoTeamRoster(demo_file_id=demo_id, demo_map_result_id=result.id, team_id=1, roster_id=roster_a,
                                      team_name_snapshot="Alpha", resolution_status=status_a))
        if roster_b is not None:
            session.add(DemoTeamRoster(demo_file_id=demo_id, demo_map_result_id=result.id, team_id=2, roster_id=roster_b,
                                      team_name_snapshot="Bravo", resolution_status=status_b))
        await session.commit()


async def compare(factory):
    async with factory() as session:
        return await TeamH2HService(session, today=TODAY).compare(1, 2)


async def test_validates_team_ids(h2h_db) -> None:
    await seed(h2h_db)
    async with h2h_db() as session:
        with pytest.raises(SameTeamH2HError): await TeamH2HService(session).compare(1, 1)
        with pytest.raises(H2HTeamNotFoundError): await TeamH2HService(session).compare(999, 2)
        with pytest.raises(H2HTeamNotFoundError): await TeamH2HService(session).compare(1, 999)


async def test_normalizes_both_database_sides_and_calculates_formulas(h2h_db) -> None:
    ra, rb = await seed(h2h_db)
    await add_map(h2h_db, 1, TODAY, 13, 9, roster_a=ra, roster_b=rb)
    await add_map(h2h_db, 2, date(2026, 2, 8), 13, 10, left=2, right=1, roster_a=ra, roster_b=rb)
    result = await compare(h2h_db); org = result.organizations
    assert (org.team_a.maps_won, org.team_b.maps_won) == (1, 1)
    assert (org.team_a.rounds_won, org.team_b.rounds_won) == (23, 22)
    assert org.effective_maps == pytest.approx(1.8)
    assert org.team_a.weighted_map_win_rate == pytest.approx(100 / 1.8)
    expected_rounds = (13 + .8 * 10) / ((13 + 9) + .8 * (10 + 13)) * 100
    assert org.team_a.weighted_round_win_rate == pytest.approx(expected_rounds)
    assert org.team_a.performance_score == pytest.approx((100 / 1.8) * .65 + expected_rounds * .35)
    assert org.team_a.h2h_rating + org.team_b.h2h_rating == pytest.approx(100)
    assert result.current_rosters.maps_played == 2


async def test_one_map_is_pulled_toward_neutral(h2h_db) -> None:
    ra, rb = await seed(h2h_db); await add_map(h2h_db, 1, TODAY, 13, 0, roster_a=ra, roster_b=rb)
    result = await compare(h2h_db)
    assert result.organizations.confidence_score == pytest.approx(30)
    assert result.organizations.team_a.h2h_rating == pytest.approx(65)
    assert result.organizations.sample_label == "very_small"
    assert "very_small_sample" in result.organizations.warnings


@pytest.mark.parametrize("age,weight", [(0, 1), (90, 1), (91, .8), (180, .8), (181, .6), (365, .6), (366, .35), (730, .35), (731, .15)])
def test_recency_weight_boundaries(age: int, weight: float) -> None:
    match = date.fromordinal(TODAY.toordinal() - age)
    assert TeamH2HService.recency_weight(match, TODAY) == (weight, False)


@pytest.mark.parametrize("count,label", [(0, "no_data"), (1, "very_small"), (2, "very_small"), (3, "small"), (5, "small"), (6, "medium"), (9, "medium"), (10, "sufficient")])
def test_sample_labels(count: int, label: str) -> None:
    assert TeamH2HService.sample_label(count) == label


@pytest.mark.parametrize("score,count,level", [(0, 0, "no_data"), (34.9, 1, "low"), (35, 1, "medium"), (69.9, 1, "medium"), (70, 1, "high")])
def test_confidence_levels(score: float, count: int, level: str) -> None:
    assert TeamH2HService.confidence_level(score, count) == level


@pytest.mark.parametrize("diff,level", [(4.99, "none"), (5, "small"), (9.99, "small"), (10, "clear"), (19.99, "clear"), (20, "strong")])
def test_advantage_levels(diff: float, level: str) -> None:
    assert TeamH2HService.advantage_level(diff) == level


async def test_history_includes_old_rosters_but_current_slice_does_not(h2h_db) -> None:
    ra, rb = await seed(h2h_db)
    async with h2h_db() as session:
        old_a = TeamRoster(team_id=1, fingerprint="c" * 64, is_current=False, source="demo", resolution_status="complete")
        old_b = TeamRoster(team_id=2, fingerprint="d" * 64, is_current=False, source="demo", resolution_status="complete")
        session.add_all([old_a, old_b]); await session.commit()
    await add_map(h2h_db, 1, TODAY, 13, 7, roster_a=old_a.id, roster_b=old_b.id)
    await add_map(h2h_db, 2, TODAY, 8, 13, roster_a=ra, roster_b=rb)
    result = await compare(h2h_db)
    assert result.organizations.maps_played == 2
    assert result.current_rosters.maps_played == 1
    assert result.current_rosters.team_b.maps_won == 1


@pytest.mark.parametrize("links", ["a", "b", "partial", "needs_review"])
async def test_current_slice_requires_both_complete_exact_links(h2h_db, links: str) -> None:
    ra, rb = await seed(h2h_db)
    await add_map(h2h_db, 1, TODAY, 13, 7, roster_a=ra if links != "b" else None,
                  roster_b=rb if links != "a" else None,
                  status_a="partial" if links == "partial" else "needs_review" if links == "needs_review" else "complete")
    result = await compare(h2h_db)
    assert result.organizations.maps_played == 1
    assert result.current_rosters.maps_played == 0


@pytest.mark.parametrize("kwargs", [
    {"round_status": "partial"}, {"score_left": None}, {"score_left": 10, "score_right": 10}, {"map_name": None},
])
async def test_invalid_maps_are_excluded_and_counted(h2h_db, kwargs: dict) -> None:
    await seed(h2h_db)
    values = {"score_left": 13, "score_right": 9, **kwargs}
    await add_map(h2h_db, 1, TODAY, values.pop("score_left"), values.pop("score_right"), **values)
    result = await compare(h2h_db)
    assert result.organizations.status == "no_meetings"
    assert result.organizations.candidate_maps_count == 1
    assert result.organizations.excluded_maps_count == 1
    assert "excluded_invalid_maps" in result.organizations.warnings


async def test_map_grouping_sorting_recent_limit_future_warning(h2h_db) -> None:
    await seed(h2h_db)
    await add_map(h2h_db, 1, date(2026, 8, 1), 13, 9, map_name="nuke")
    await add_map(h2h_db, 2, date(2026, 8, 2), 13, 8, map_name="mirage")
    await add_map(h2h_db, 3, date(2026, 8, 9), 7, 13, map_name="mirage", overtime=True)
    async with h2h_db() as session:
        result = await TeamH2HService(session, today=TODAY).compare(1, 2, recent_limit=2)
    assert [(m.map_name, m.maps_played) for m in result.organizations.maps] == [("mirage", 2), ("nuke", 1)]
    assert [m.demo_file_id for m in result.organizations.recent_maps] == [3, 2]
    assert result.organizations.recent_maps[0].recency_weight == 1
    assert "future_match_date" in result.organizations.warnings


async def test_empty_and_current_roster_unavailable_statuses(h2h_db) -> None:
    await seed(h2h_db, current=False)
    result = await compare(h2h_db)
    assert result.organizations.status == "no_meetings"
    assert result.current_rosters.status == "current_roster_unavailable"


async def test_current_rosters_never_met(h2h_db) -> None:
    await seed(h2h_db); result = await compare(h2h_db)
    assert result.current_rosters.status == "current_rosters_never_met"
    assert result.current_rosters.team_a.h2h_rating is None


@pytest.fixture
async def h2h_api(h2h_db):
    app = create_app()
    async def override():
        async with h2h_db() as session: yield session
    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_h2h_api_contract_validation_and_legacy_endpoint(h2h_db, h2h_api) -> None:
    ra, rb = await seed(h2h_db); await add_map(h2h_db, 1, TODAY, 13, 9, roster_a=ra, roster_b=rb)
    response = await h2h_api.get("/api/v1/analysis/compare/teams/1/2/h2h?recent_limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["organizations"]["team_a"]["h2h_rating"] == 60.7
    assert len(payload["organizations"]["recent_maps"]) == 1
    assert (await h2h_api.get("/api/v1/analysis/compare/teams/1/2/h2h?recent_limit=20")).status_code == 200
    assert (await h2h_api.get("/api/v1/analysis/compare/teams/1/2/h2h?recent_limit=0")).status_code == 422
    assert (await h2h_api.get("/api/v1/analysis/compare/teams/1/1/h2h")).status_code == 400
    assert (await h2h_api.get("/api/v1/analysis/compare/teams/1/99/h2h")).status_code == 404
    legacy = await h2h_api.get("/api/v1/analysis/compare/teams/1/2/current-rosters")
    assert legacy.status_code == 200
    assert legacy.json()["head_to_head"]["maps_played"] == 1
