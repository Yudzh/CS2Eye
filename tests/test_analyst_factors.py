from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.team import AnalystFactor, Player, Team, TeamParticipantMembership
from cs2eye.services.analyst_context_service import AnalystContextService

NOW = datetime(2026, 8, 21, 10, tzinfo=UTC)


@pytest.fixture
async def client_session() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        app = create_app()
        async def override(): yield session
        app.dependency_overrides[get_db_session] = override
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, session
    await engine.dispose()


async def seed(session: AsyncSession):
    session.add_all([Team(id=1,bo3_id=1,bo3_slug="spirit",name="Spirit"),Team(id=2,bo3_id=2,bo3_slug="other",name="Other")])
    for pid,name,team,kind in [(10,"donk",1,"player"),(11,"zont1x",1,"player"),(12,"hally",1,"coach"),(20,"enemy",2,"player")]:
        session.add(Player(id=pid,bo3_id=pid,bo3_slug=name,nickname=name))
        session.add(TeamParticipantMembership(team_id=team,player_id=pid,participant_type=kind,is_active=True))
    await session.commit()


async def test_crud_relations_filters_and_temporal_safety(client_session):
    client,session=client_session;await seed(session)
    payload={"team_id":1,"factor_type":"negative","text":"Поздние ротации B","category":"ct_defense","map_name":"dust2","environment":"lan","player_ids":[10,11],"coach_id":12,"valid_until":(NOW+timedelta(days=4)).isoformat()}
    created=await client.post("/api/v1/analyst-factors",json=payload);assert created.status_code==201
    body=created.json();assert [p["nickname"] for p in body["players"]]==["donk","zont1x"];assert body["coach"]["nickname"]=="hally"
    assert len((await client.get("/api/v1/analyst-factors",params={"team_id":1,"map_name":"dust2","environment":"lan","player_id":10})).json())==1
    patched=await client.patch(f'/api/v1/analyst-factors/{body["id"]}',json={"factor_type":"positive","player_ids":[],"coach_id":None});assert patched.json()["players"]==[];assert patched.json()["factor_type"]=="positive"
    factor=await session.get(AnalystFactor,body["id"]);factor.created_at=NOW-timedelta(days=1);await session.commit()
    context=await AnalystContextService(session).structured(1,as_of=NOW+timedelta(days=1));assert context["positive"][0]["text"]==payload["text"]
    future=await AnalystContextService(session).structured(1,as_of=datetime(2020,1,1,tzinfo=UTC));assert future["positive"]==[]


async def test_invalid_team_player_map_and_expired_inactive(client_session):
    client,session=client_session;await seed(session)
    base={"team_id":1,"factor_type":"positive","text":"x","environment":"any"}
    assert (await client.post("/api/v1/analyst-factors",json={**base,"team_id":999})).status_code==404
    assert (await client.post("/api/v1/analyst-factors",json={**base,"player_ids":[20]})).status_code==422
    assert (await client.post("/api/v1/analyst-factors",json={**base,"map_name":"dust_22"})).status_code==422
    expired=(await client.post("/api/v1/analyst-factors",json={**base,"valid_until":(NOW-timedelta(days=1)).isoformat()})).json()
    inactive=(await client.post("/api/v1/analyst-factors",json={**base,"is_active":False})).json()
    relevant,_=await AnalystContextService(session).relevant(1,as_of=NOW)
    assert expired["id"] not in {x.id for x in relevant};assert inactive["id"] not in {x.id for x in relevant}
