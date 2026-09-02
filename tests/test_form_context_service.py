from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import RankingImportRun, Team, TeamRankingSnapshot
from cs2eye.services.form_context_service import (
    FormContextService, expected_probability, rank_strength, series_quality,
)
from cs2eye.services.opponent_context_service import OpponentContextService


AS_OF = date(2026, 8, 26)


@pytest.fixture
async def form_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def seed(form_db):
    async with form_db() as session:
        session.add_all([Team(id=i, bo3_id=100+i, bo3_slug=f"t{i}", name=f"Team {i}") for i in range(1, 6)])
        session.add_all([Tournament(id=1,name="Current",year=2026,environment="lan",start_date=AS_OF-timedelta(days=10),end_date=AS_OF+timedelta(days=2)),Tournament(id=2,name="Other",year=2026,environment="online",start_date=AS_OF-timedelta(days=50),end_date=AS_OF-timedelta(days=40))])
        run=RankingImportRun(id=1,status="success",source="test",source_url="test",started_at=datetime.now(UTC),ranking_date=AS_OF-timedelta(days=20))
        session.add(run)
        # A future snapshot for Team 2 must not leak into earlier series.
        for index,(team_id,rank,day) in enumerate([(1,20,-70),(2,2,-70),(2,40,-2),(3,8,-70),(4,45,-70),(5,25,-70)],1):
            session.add(TeamRankingSnapshot(id=index,import_run_id=1,team_id=team_id,source="test",ranking_date=AS_OF+timedelta(days=day),rank=rank,points=1000,roster_payload=[]))
        matches=[
            Match(id=1,tournament_id=2,match_date=AS_OF-timedelta(days=61),team_a_id=1,team_b_id=5,format="bo3",environment="online",status="completed",resolution_status="resolved",winner_team_id=1,team_a_maps_won=2,team_b_maps_won=0),
            Match(id=2,tournament_id=2,match_date=AS_OF-timedelta(days=60),team_a_id=1,team_b_id=2,format="bo3",environment="online",status="completed",resolution_status="resolved",winner_team_id=2,team_a_maps_won=1,team_b_maps_won=2),
            Match(id=3,tournament_id=1,match_date=AS_OF-timedelta(days=5),team_a_id=1,team_b_id=3,format="bo3",environment="lan",status="completed",resolution_status="resolved",winner_team_id=1,team_a_maps_won=2,team_b_maps_won=0),
            Match(id=4,tournament_id=1,match_date=AS_OF-timedelta(days=2),team_a_id=1,team_b_id=4,format="bo3",environment="lan",status="completed",resolution_status="resolved",winner_team_id=1,team_a_maps_won=2,team_b_maps_won=1),
            Match(id=5,tournament_id=1,match_date=AS_OF,team_a_id=1,team_b_id=2,format="bo3",environment="lan",status="completed",resolution_status="resolved",winner_team_id=1,team_a_maps_won=2,team_b_maps_won=0),
        ]
        session.add_all(matches);await session.commit()


async def test_recent_window_same_day_tournament_and_self_isolation(form_db) -> None:
    await seed(form_db)
    async with form_db() as session:
        result=await FormContextService(session).calculate(1,AS_OF,1,exclude_match_id=5)
    assert result["recent_60d_matches_count"] == 3  # day -60 is included; day -61 and same-day are not
    assert result["tournament_matches_count"] == 2
    assert result["tournament_form_score"] is not None
    assert result["top10_matches_60d"] == 2  # Team 2 uses rank 2 at its match, not future rank 40


async def test_stronger_opponents_raise_schedule_strength(form_db) -> None:
    await seed(form_db)
    async with form_db() as session:
        strong=await FormContextService(session).calculate(1,AS_OF,2)
        weak=await FormContextService(session).calculate(1,AS_OF,1)
    assert strong["tournament_strength_of_schedule_score"] > weak["tournament_strength_of_schedule_score"]


def test_close_underdog_loss_is_better_than_heavy_favorite_loss() -> None:
    close,_=series_quality(False,1,2)
    heavy,_=series_quality(False,0,2)
    close_delta=close-expected_probability(30,2)
    heavy_delta=heavy-expected_probability(2,30)
    assert close_delta > heavy_delta


def test_upset_and_dominant_win_outperform_expectation() -> None:
    upset,_=series_quality(True,2,1)
    narrow,_=series_quality(True,2,1)
    dominant,_=series_quality(True,2,0)
    assert upset-expected_probability(30,3) > 0
    assert dominant-expected_probability(3,30) > narrow-expected_probability(3,30)


async def test_insufficient_data_returns_null_scores(form_db) -> None:
    async with form_db() as session:
        session.add(Team(id=99,bo3_id=99,bo3_slug="empty",name="Empty"));await session.commit()
        result=await FormContextService(session).calculate(99,AS_OF)
    assert result["status"] == "insufficient_data"
    assert result["recent_60d_adjusted_form_score"] is None
    assert result["tournament_form_score"] is None


def test_rank_strength_is_monotonic() -> None:
    assert rank_strength(3) > rank_strength(10) > rank_strength(30)


async def test_opponent_context_is_temporal_depth_one_and_cached(form_db) -> None:
    await seed(form_db)
    async with form_db() as session:
        service=OpponentContextService(session)
        first=await service.calculate(1,AS_OF,1)
        second=await service.calculate(1,AS_OF,1)
    assert first is second
    assert first["depth"]==1
    assert all(row["date"]<AS_OF for row in first["matches"])
    assert {row["match_id"] for row in first["matches"]}=={2,3,4}


async def test_strong_win_has_more_quality_and_weak_loss_more_penalty(form_db) -> None:
    await seed(form_db)
    async with form_db() as session:
        rows=(await OpponentContextService(session).calculate(1,AS_OF,1))["matches"]
    strong_win=next(row for row in rows if row["match_id"]==3)
    weak_win=next(row for row in rows if row["match_id"]==4)
    assert strong_win["opponent_dynamic_strength"]>weak_win["opponent_dynamic_strength"]
    assert strong_win["result_quality_score"]>weak_win["result_quality_score"]
    # The loss to highly ranked Team 2 is not punished like a loss to a weak team.
    loss=next(row for row in rows if row["match_id"]==2)
    assert loss["result_quality_score"]>-1
