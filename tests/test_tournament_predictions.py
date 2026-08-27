from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import TournamentMatchPrediction, TournamentPredictionRun
from cs2eye.models.team import Team
from cs2eye.services.tournament_prediction_service import TournamentPredictionService, invalidate_tournament_predictions


@pytest.fixture
async def prediction_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Team(id=i, bo3_id=100 + i, bo3_slug=f"t{i}", name=f"Team {i}") for i in range(1, 5)])
        tournament = Tournament(id=1, name="Future", year=2026, environment="lan", structure_type="single_elimination")
        session.add(tournament)
        qf1 = Match(id=1, tournament_id=1, match_date=date(2026, 9, 1), team_a_id=1, team_b_id=2,
                    format="bo3", stage="quarterfinal", status="scheduled", round_number=1,
                    bracket_position=1, next_match_id=3, next_match_slot="team_a")
        qf2 = Match(id=2, tournament_id=1, match_date=date(2026, 9, 1), team_a_id=3, team_b_id=4,
                    format="bo3", stage="quarterfinal", status="scheduled", round_number=1,
                    bracket_position=2, next_match_id=3, next_match_slot="team_b")
        final = Match(id=3, tournament_id=1, match_date=date(2026, 9, 2), format="bo3", stage="final",
                      status="scheduled", round_number=2, bracket_position=1)
        session.add_all([qf1, qf2, final]); await session.commit()
    yield factory
    await engine.dispose()


def available(winner: int):
    async def predict(_session, *, a, b, **_kwargs):
        p = .7 if a == winner else .3 if b == winner else .6
        return {"prediction_status": "available", "model_version": "win_v1",
                "team_a": {"id": a, "probability": p}, "team_b": {"id": b, "probability": 1-p},
                "confidence": .72}
    return predict


async def test_projected_winners_advance_without_creating_matches(prediction_db) -> None:
    async with prediction_db() as session:
        before = await session.scalar(select(func.count(Match.id)))
        run = await TournamentPredictionService(session, available(1)).generate(1)
        await session.commit()
        rows = list((await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id).order_by(TournamentMatchPrediction.id))).all())
        after = await session.scalar(select(func.count(Match.id)))
        actual = await session.get(Match, 3)
    assert before == after == 3
    assert actual.team_a_id is None and actual.team_b_id is None
    assert [(row.prediction_type, row.team_a_id, row.team_b_id) for row in rows] == [
        ("actual_match", 1, 2), ("actual_match", 3, 4), ("projected_match", 1, 3)]
    assert rows[-1].model_version == "win_v1" and float(rows[-1].confidence) == pytest.approx(.72)


async def test_actual_winner_has_priority_and_old_run_is_preserved(prediction_db) -> None:
    async with prediction_db() as session:
        service = TournamentPredictionService(session, available(1))
        first = await service.generate(1); await session.commit()
        qf1 = await session.get(Match, 1); qf1.status = "completed"; qf1.winner_team_id = 2
        second = await service.generate(1); await session.commit()
        final = (await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == second.id,
            TournamentMatchPrediction.stage == "final"))).one()
        runs = list((await session.scalars(select(TournamentPredictionRun).order_by(TournamentPredictionRun.id))).all())
    assert final.team_a_id == 2
    assert len(runs) == 2 and runs[0].outdated is True and runs[1].outdated is False
    assert first.id != second.id


async def test_insufficient_data_leaves_downstream_slot_tbd(prediction_db) -> None:
    async def predict(_session, *, a, b, **_kwargs):
        if {a, b} == {1, 2}:
            return {"prediction_status": "insufficient_data", "model_version": "win_v1",
                    "team_a": {"id": a, "probability": None}, "team_b": {"id": b, "probability": None}, "confidence": .1}
        return await available(3)(_session, a=a, b=b)
    async with prediction_db() as session:
        run = await TournamentPredictionService(session, predict).generate(1); await session.commit()
        final = (await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id,
            TournamentMatchPrediction.stage == "final"))).one()
    assert final.team_a_id is None and final.team_b_id == 3
    assert final.predicted_winner_id is None and final.status == "insufficient_data"


async def test_actual_result_change_invalidates_current_prediction(prediction_db) -> None:
    async with prediction_db() as session:
        run = await TournamentPredictionService(session, available(1)).generate(1)
        await session.commit()
        await invalidate_tournament_predictions(session, 1)
        await session.commit()
        refreshed = await session.get(TournamentPredictionRun, run.id)
        rows = list((await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id))).all())
    assert refreshed.outdated is True
    assert rows and all(row.invalidated_at is not None for row in rows)


async def test_known_group_match_is_predicted(prediction_db) -> None:
    async with prediction_db() as session:
        for item in (await session.scalars(select(Match))).all():
            item.stage = "group"
        await session.commit()
        run = await TournamentPredictionService(session, available(1)).generate(1)
        await session.commit()
        rows = list((await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id))).all())
    assert len(rows) == 3
    assert rows[0].status == "available"


async def test_untrained_model_falls_back_to_matchup_score(prediction_db) -> None:
    async def untrained(_session, **kwargs):
        return {"prediction_status": "model_not_trained", "model_version": None,
                "team_a": {"id": kwargs["a"], "probability": None},
                "team_b": {"id": kwargs["b"], "probability": None}, "confidence": 0}
    async def matchup(a, b, *_args):
        return {"status": "available", "model_version": "matchup_v1", "reliability": .7,
                "team_a": {"id": a, "score": 61}, "team_b": {"id": b, "score": 39}}
    async with prediction_db() as session:
        run = await TournamentPredictionService(session, untrained, matchup).generate(1)
        await session.commit()
        first = (await session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id).order_by(TournamentMatchPrediction.id))).first()
    assert first.status == "comparison_fallback"
    assert first.prediction_basis == "matchup_score"
    assert first.team_a_score == 61 and first.team_a_probability is None
    assert first.predicted_winner_id == first.team_a_id
