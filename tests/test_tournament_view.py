from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.demo import DemoPlayerStat
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.team import Team
from cs2eye.services.tournament_view_service import TournamentViewService


@pytest.fixture
async def match_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Team(id=1, bo3_id=101, bo3_slug="alpha", name="Alpha", is_analytics_active=True),
            Team(id=2, bo3_id=102, bo3_slug="bravo", name="Bravo", is_analytics_active=True),
        ])
        await session.commit()
    yield factory
    await engine.dispose()


async def seed_bracket(factory):
    async with factory() as session:
        for team_id, name in ((3, "Charlie"), (4, "Delta")):
            if await session.get(Team, team_id) is None:
                session.add(Team(id=team_id, bo3_id=100 + team_id, bo3_slug=name.lower(), name=name, is_analytics_active=True))
        tournament = Tournament(name="Bracket Cup", year=2026, environment="lan", structure_type="single_elimination", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3))
        session.add(tournament); await session.flush()
        qf1 = Match(tournament_id=tournament.id, match_date=date(2026, 8, 1), team_a_id=1, team_b_id=2, winner_team_id=1, team_a_maps_won=2, team_b_maps_won=0, format="bo3", stage="quarterfinal", status="completed", resolution_status="resolved", is_playoff=True)
        qf2 = Match(tournament_id=tournament.id, match_date=date(2026, 8, 1), team_a_id=3, team_b_id=4, winner_team_id=3, team_a_maps_won=2, team_b_maps_won=1, format="bo3", stage="quarterfinal", status="completed", resolution_status="resolved", is_playoff=True)
        sf = Match(tournament_id=tournament.id, match_date=date(2026, 8, 2), team_a_id=1, team_b_id=3, winner_team_id=1, team_a_maps_won=2, team_b_maps_won=1, format="bo3", stage="semifinal", status="completed", resolution_status="resolved", is_playoff=True)
        final = Match(tournament_id=tournament.id, match_date=date(2026, 8, 3), team_a_id=1, team_b_id=4, format="bo3", stage="final", status="scheduled", resolution_status="resolved", is_playoff=True)
        session.add_all([qf1, qf2, sf, final]); await session.commit()
        return tournament.id, qf1.id, qf2.id, sf.id, final.id


@pytest.fixture
async def tournament_api(match_db):
    app = create_app()
    async def override():
        async with match_db() as session: yield session
    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_tournament_list_and_view_are_filtered(match_db, tournament_api) -> None:
    tournament_id, qf1, _, sf, _ = await seed_bracket(match_db)
    response = await tournament_api.get("/api/v1/tournaments")
    assert response.status_code == 200
    assert any(item["id"] == tournament_id for item in response.json()["items"])
    view = (await tournament_api.get(f"/api/v1/tournaments/{tournament_id}/view")).json()
    assert {item["id"] for item in view["matches"]} == {qf1, qf1 + 1, sf, sf + 1}
    assert view["summary"]["series_count"] == 4
    assert {tuple((link["from_match_id"], link["to_match_id"])) for link in view["bracket_links"]} >= {(qf1, sf)}


async def test_ambiguous_next_match_is_not_linked(match_db) -> None:
    tournament_id, qf1, _, sf, _ = await seed_bracket(match_db)
    async with match_db() as session:
        session.add(Match(tournament_id=tournament_id, match_date=date(2026, 8, 2), team_a_id=1, team_b_id=4, format="bo3", stage="semifinal", resolution_status="resolved", is_playoff=True))
        await session.commit()
    async with match_db() as session:
        view = await TournamentViewService(session).view(tournament_id)
        assert not any(source == "inferred" and source_id == qf1 for source_id, _, source in view.links)
        assert any(problem.match_id == qf1 and problem.code == "layout_unresolved" for problem in view.problems)


async def test_manual_layout_and_stage_patch_preserve_analytics(match_db, tournament_api) -> None:
    tournament_id, qf1, _, sf, _ = await seed_bracket(match_db)
    async with match_db() as session:
        before = await session.scalar(select(func.count(DemoPlayerStat.id)))
    response = await tournament_api.patch(f"/api/v1/matches/{qf1}", json={"stage":"semifinal", "round_number":2, "round_label":"Upper SF", "bracket_section":"upper", "bracket_position":1, "next_match_id":sf, "next_match_slot":"team_a"})
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "semifinal" and body["next_match_id"] == sf and body["bracket_section"] == "upper"
    async with match_db() as session:
        after = await session.scalar(select(func.count(DemoPlayerStat.id)))
        assert before == after


async def test_tournament_structure_patch(match_db, tournament_api) -> None:
    tournament_id, *_ = await seed_bracket(match_db)
    response = await tournament_api.patch(f"/api/v1/tournaments/{tournament_id}", json={"structure_type":"groups_playoff"})
    assert response.status_code == 200
    assert response.json()["structure_type"] == "groups_playoff"

async def test_create_future_tournament_participants_and_scheduled_match(match_db, tournament_api) -> None:
    response = await tournament_api.post("/api/v1/tournaments", json={"name":"Future Cup","year":2026,"tier":"S","environment":"lan","start_date":"2026-11-02","end_date":"2026-11-08","structure_type":"single_elimination","team_ids":[1,2],"matches":[{"team_a_id":1,"team_b_id":2,"match_date":"2026-11-02","format":"bo3","stage":"quarterfinal","round_number":1,"round_label":"Quarterfinal","bracket_section":"main","bracket_position":1}]})
    assert response.status_code == 201
    tournament_id = response.json()["id"]
    async with match_db() as session:
        participants = list((await session.execute(select(TournamentTeam).where(TournamentTeam.tournament_id==tournament_id))).scalars())
        assert {item.team_id for item in participants} == {1,2}
    view = (await tournament_api.get(f"/api/v1/tournaments/{tournament_id}/view")).json()
    match = view["matches"][0]
    assert match["status"] == "scheduled" and match["maps"] == [] and match["score"] == {"team_a":0,"team_b":0}
    assert not {"demo_missing","veto_missing"} & {problem["code"] for problem in view["problems"]}
    assert view["summary"]["participant_count"] == 2 and view["summary"]["scheduled_series"] == 1

@pytest.mark.parametrize("change", [
    {"team_ids":[1,1]},
    {"matches":[{"team_a_id":1,"team_b_id":1,"match_date":"2026-11-02","format":"bo3"}]},
    {"matches":[{"team_a_id":1,"team_b_id":3,"match_date":"2026-11-02","format":"bo3"}]},
    {"matches":[{"team_a_id":1,"team_b_id":2,"match_date":"2026-12-02","format":"bo3"}]},
    {"start_date":"2026-11-09"},
])
async def test_future_tournament_validation(tournament_api, change) -> None:
    payload={"name":"Invalid Cup","year":2027,"environment":"online","start_date":"2026-11-02","end_date":"2026-11-08","structure_type":"swiss","team_ids":[1,2],"matches":[]};payload.update(change)
    assert (await tournament_api.post("/api/v1/tournaments",json=payload)).status_code == 422

async def test_add_scheduled_match_to_existing_tournament(tournament_api) -> None:
    created = await tournament_api.post("/api/v1/tournaments", json={"name":"Separate Flow","year":2028,"environment":"lan","start_date":"2028-06-01","end_date":"2028-06-05","structure_type":"single_elimination","team_ids":[1,2],"matches":[]})
    tournament_id = created.json()["id"]
    response = await tournament_api.post(f"/api/v1/tournaments/{tournament_id}/matches", json={"team_a_id":1,"team_b_id":2,"match_date":"2028-06-02","format":"bo3","stage":"semifinal","round_number":1,"round_label":"Semifinal","bracket_section":"main","bracket_position":1})
    assert response.status_code == 201
    assert response.json()["status"] == "scheduled"
