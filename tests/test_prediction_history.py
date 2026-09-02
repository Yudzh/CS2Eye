from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team
from cs2eye.services.prediction_history_service import PredictionHistoryService


@pytest.fixture
async def history_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        tournament = Tournament(id=1, name="Cup", year=2026, environment="lan")
        session.add_all([
            tournament,
            Team(id=1, bo3_id=1, bo3_slug="alpha", name="Alpha", is_analytics_active=True),
            Team(id=2, bo3_id=2, bo3_slug="bravo", name="Bravo", is_analytics_active=True),
            Match(id=10, tournament_id=1, match_date=date(2026, 9, 1), team_a_id=1, team_b_id=2,
                  format="bo3", stage="group", environment="lan", status="scheduled", resolution_status="resolved"),
        ])
        await session.commit()
    yield factory
    await engine.dispose()


async def test_capture_saves_all_three_snapshots_and_never_recalculates(history_db, monkeypatch) -> None:
    import cs2eye.services.prediction_history_service as module
    state = {"strength": (60.0, 40.0), "matchup": (45.0, 55.0), "ml": (.61, .39)}
    async def compare(self, a, b):
        return SimpleNamespace(team_a=SimpleNamespace(strength=SimpleNamespace(team_strength_score=state["strength"][0])), team_b=SimpleNamespace(strength=SimpleNamespace(team_strength_score=state["strength"][1])))
    async def matchup(self, *args):
        winner = 1 if state["matchup"][0] > 53 else 2 if state["matchup"][0] < 47 else None
        return {"model_version":"matchup_v1","team_a": {"score": state["matchup"][0]}, "team_b": {"score": state["matchup"][1]}, "reliability":.8,"advantage":{"team_id":winner},"factors":[{"key":"map_veto","label":"Карты и вето","score":60,"weight":.3,"effective_weight":.3,"impact":3,"confidence":.9,"available":True}]}
    async def ml(*args, **kwargs):
        return {"prediction_status": "available", "model_version":"ml_v1", "feature_schema_version":"features_v2", "team_a": {"probability": state["ml"][0]}, "team_b": {"probability": state["ml"][1]}}
    monkeypatch.setattr(module.TeamComparisonService, "compare", compare)
    monkeypatch.setattr(module.MatchupService, "calculate", matchup)
    monkeypatch.setattr(module, "predict_win_probability", ml)
    as_of = datetime(2026, 8, 31, 10, tzinfo=UTC)
    async with history_db() as session:
        service = PredictionHistoryService(session)
        first = await service.capture(10, as_of=as_of)
        await session.commit()
        assert (float(first.team_strength_a), float(first.team_strength_b), first.team_strength_winner_id) == (60, 40, 1)
        assert (float(first.matchup_a), float(first.matchup_b), first.matchup_winner_id) == (45, 55, 2)
        assert first.matchup_factors["factors"]["map_veto"]["contribution"] == 2.4
        assert (float(first.ml_a_probability), float(first.ml_b_probability), first.ml_winner_id) == (.61, .39, 1)
        assert first.source == "pre_match"
        assert (first.team_strength_model_version, first.matchup_model_version,
                first.ml_model_version, first.ml_feature_schema_version) == ("v2", "matchup_v1", "ml_v1", "features_v2")
        state.update(strength=(1, 99), matchup=(99, 1), ml=(.1, .9))
        second = await service.capture(10, as_of=datetime(2026, 9, 1, tzinfo=UTC))
        assert second.id == first.id
        assert (float(second.team_strength_a), second.team_strength_winner_id) == (60, 1)
        assert (float(second.matchup_a), second.matchup_winner_id) == (45, 2)
        assert second.matchup_factors["factors"]["map_veto"]["contribution"] == 2.4
        assert (float(second.ml_a_probability), second.ml_winner_id) == (.61, 1)


async def test_history_result_consensus_accuracy_missing_ml_pending_and_filters(history_db) -> None:
    async with history_db() as session:
        pending = PredictionHistorySnapshot(match_id=10, tournament_id=1, as_of=datetime(2026, 8, 31, tzinfo=UTC), team_a_id=1, team_b_id=2,
            team_strength_a=60, team_strength_b=40, team_strength_winner_id=1,
            matchup_a=55, matchup_b=45, matchup_winner_id=1,
            ml_a_probability=.49, ml_b_probability=.51, ml_winner_id=2)
        completed_match = Match(id=11, tournament_id=1, match_date=date(2026, 8, 30), team_a_id=1, team_b_id=2,
            format="bo3", stage="group", environment="lan", status="completed", resolution_status="resolved", winner_team_id=2, team_a_maps_won=1, team_b_maps_won=2)
        missing_ml = PredictionHistorySnapshot(match_id=11, tournament_id=1, as_of=datetime(2026, 8, 29, tzinfo=UTC), team_a_id=1, team_b_id=2,
            team_strength_a=60, team_strength_b=40, team_strength_winner_id=1,
            matchup_a=40, matchup_b=60, matchup_winner_id=2,
            ml_a_probability=None, ml_b_probability=None, ml_winner_id=None)
        unanimous_match = Match(id=12, tournament_id=1, match_date=date(2026, 8, 29), team_a_id=1, team_b_id=2,
            format="bo3", stage="group", environment="lan", status="completed", resolution_status="resolved", winner_team_id=1, team_a_maps_won=2, team_b_maps_won=0)
        unanimous = PredictionHistorySnapshot(match_id=12, tournament_id=1, as_of=datetime(2026, 8, 28, tzinfo=UTC), team_a_id=1, team_b_id=2,
            team_strength_a=60, team_strength_b=40, team_strength_winner_id=1,
            matchup_a=60, matchup_b=40, matchup_winner_id=1,
            ml_a_probability=.57, ml_b_probability=.43, ml_winner_id=1)
        retrospective_match = Match(id=13, tournament_id=1, match_date=date(2026, 8, 28), team_a_id=1, team_b_id=2,
            format="bo3", stage="group", environment="lan", status="completed", resolution_status="resolved", winner_team_id=1, team_a_maps_won=2, team_b_maps_won=0)
        retrospective = PredictionHistorySnapshot(match_id=13, tournament_id=1, as_of=datetime(2026, 8, 27, tzinfo=UTC), source="retrospective", team_a_id=1, team_b_id=2,
            team_strength_a=1, team_strength_b=99, team_strength_winner_id=2,
            matchup_a=1, matchup_b=99, matchup_winner_id=2,
            ml_a_probability=.01, ml_b_probability=.99, ml_winner_id=2)
        session.add_all([pending, completed_match, missing_ml, unanimous_match, unanimous, retrospective_match, retrospective])
        await session.commit()
        service = PredictionHistoryService(session)
        result = await service.history()
        by_match = {item["match_id"]: item for item in result["items"]}
        assert by_match[10]["team_strength"]["correct"] is None
        assert by_match[10]["consensus"] == {"winner_id": 1, "winner": "Alpha", "votes": 2, "total": 3, "correct": None}
        assert by_match[11]["team_strength"]["correct"] is False and by_match[11]["matchup"]["correct"] is True
        assert by_match[11]["ml"]["predicted_winner_id"] is None
        assert by_match[12]["consensus"]["votes"] == 3 and by_match[12]["consensus"]["correct"] is True
        assert result["statistics"]["team_strength"] == {"correct": 1, "total": 2, "accuracy": .5}
        assert result["statistics"]["matchup"] == {"correct": 2, "total": 2, "accuracy": 1.0}
        assert result["statistics"]["ml"] == {"correct": 1, "total": 1, "accuracy": 1.0}
        assert result["statistics"]["consensus_3_3"] == {"correct": 1, "total": 1, "accuracy": 1.0}
        assert result["statistics"]["snapshot_counts"] == {"pre_match": 3, "retrospective": 1, "completed_pre_match": 2}
        assert by_match[10]["evaluation"] == {"eligible": True, "reason": None}
        assert by_match[13]["evaluation"] == {"eligible": False, "reason": "retrospective"}
        assert by_match[13]["ml"]["evaluation_status"] == "not_evaluable_retrospective"
        assert by_match[13]["ml"]["predicted_winner_id"] is None
        assert by_match[13]["versions"] == {"team_strength": None, "matchup": None, "ml": None, "ml_feature_schema": None}
        assert [item["match_id"] for item in (await service.history(status="future"))["items"]] == [10]
        assert [item["match_id"] for item in (await service.history(consensus_3_3=True))["items"]] == [12]
        assert [item["match_id"] for item in (await service.history(match_date=date(2026, 8, 30)))["items"]] == [11]
        assert {item["match_id"] for item in (await service.history(source="pre_match"))["items"]} == {10, 11, 12}
        retrospective_only = await service.history(source="retrospective")
        assert [item["match_id"] for item in retrospective_only["items"]] == [13]
        assert retrospective_only["statistics"]["team_strength"]["total"] == 2


async def test_capture_tournament_processes_only_new_scheduled_matches_with_teams(history_db, monkeypatch) -> None:
    called = []
    async with history_db() as session:
        session.add_all([
            Match(id=13, tournament_id=1, match_date=date(2026, 9, 2), team_a_id=1, team_b_id=2,
                  format="bo3", stage="group", environment="lan", status="scheduled", resolution_status="resolved"),
            Match(id=14, tournament_id=1, match_date=date(2026, 9, 2), team_a_id=None, team_b_id=None,
                  format="bo3", stage="group", environment="lan", status="scheduled", resolution_status="resolved"),
            PredictionHistorySnapshot(match_id=10, tournament_id=1, as_of=datetime(2026, 8, 31, tzinfo=UTC), team_a_id=1, team_b_id=2,
                team_strength_a=60, team_strength_b=40, team_strength_winner_id=1,
                matchup_a=60, matchup_b=40, matchup_winner_id=1,
                ml_a_probability=.6, ml_b_probability=.4, ml_winner_id=1),
        ])
        await session.commit()
        async def fake_capture(self, match_id, as_of=None):
            called.append(match_id)
            return SimpleNamespace(id=99, match_id=match_id)
        monkeypatch.setattr(PredictionHistoryService, "capture", fake_capture)
        result = await PredictionHistoryService(session).capture_tournament(1)
        assert called == [13]
        assert result["eligible"] == 2
        assert result["created"] == 1 and result["existing"] == 1


async def test_completed_match_can_be_captured_only_as_strict_retrospective(history_db, monkeypatch) -> None:
    import cs2eye.services.prediction_history_service as module
    async with history_db() as session:
        match = await session.get(Match, 10)
        match.status = "completed"; match.winner_team_id = 2; match.team_a_maps_won = 1; match.team_b_maps_won = 2
        await session.commit()
        with pytest.raises(ValueError, match="после завершения"):
            await PredictionHistoryService(session).capture(10)
        async def historical(self, *args):
            return {"model_version":"matchup_v1","team_a":{"score":44},"team_b":{"score":56},"team_strength":{"team_a_score":48,"team_b_score":52},"reliability":.8,"advantage":{"team_id":2},"factors":[]}
        async def ml(*args, **kwargs):
            raise AssertionError("retrospective capture must not invoke current ML")
        monkeypatch.setattr(module.AnalyticsAsOfService,"calculate",historical)
        monkeypatch.setattr(module,"predict_win_probability",ml)
        row = await PredictionHistoryService(session).capture(10, retrospective=True)
        assert row.source == "retrospective"
        assert row.as_of.date() == match.match_date
        assert (row.team_strength_winner_id,row.matchup_winner_id,row.ml_winner_id) == (2,2,None)
        assert row.ml_a_probability is None and row.ml_b_probability is None
        item = (await PredictionHistoryService(session).history())["items"][0]
        assert item["evaluation"] == {"eligible": False, "reason": "retrospective"}
        assert item["ml"]["evaluation_status"] == "not_evaluable_retrospective"


async def test_conflict_types_statistics_and_filters(history_db) -> None:
    async with history_db() as session:
        cases = [
            # id, status, actual, TS, Matchup, ML, values are intentionally strong.
            (11, "completed", 2, 1, 1, 2, (70, 30, 65, 35, .30, .70)),
            (12, "completed", 1, 1, 2, 1, (70, 30, 35, 65, .70, .30)),
            (13, "completed", 2, 1, 2, 2, (70, 30, 35, 65, .30, .70)),
            (14, "completed", 1, 1, 1, 1, (70, 30, 65, 35, .70, .30)),
            (15, "completed", 1, 1, 2, None, (70, 30, 35, 65, None, None)),
            # Future conflicts are displayed but excluded from accuracy.
            (16, "scheduled", None, 1, 1, 2, (70, 30, 65, 35, .30, .70)),
            # Real conflict, but below the configured strong threshold.
            (17, "completed", 2, 1, 1, 2, (51, 49, 51, 49, .49, .51)),
        ]
        for match_id, status, actual, ts, matchup, ml, values in cases:
            session.add(Match(id=match_id, tournament_id=1, match_date=date(2026, 8, match_id),
                team_a_id=1, team_b_id=2, format="bo3", stage="group", environment="lan",
                status=status, resolution_status="resolved", winner_team_id=actual,
                team_a_maps_won=2 if actual == 1 else 0, team_b_maps_won=2 if actual == 2 else 0))
            session.add(PredictionHistorySnapshot(match_id=match_id, tournament_id=1,
                as_of=datetime(2026, 8, match_id - 1, tzinfo=UTC), team_a_id=1, team_b_id=2,
                team_strength_a=values[0], team_strength_b=values[1], team_strength_winner_id=ts,
                matchup_a=values[2], matchup_b=values[3], matchup_winner_id=matchup,
                ml_a_probability=values[4], ml_b_probability=values[5], ml_winner_id=ml,
                actual_winner_id=actual))
        await session.commit()
        service = PredictionHistoryService(session)
        result = await service.history()
        by_match = {item["match_id"]: item for item in result["items"]}
        assert by_match[11]["conflict"]["type"] == "ts_matchup_vs_ml"
        assert by_match[12]["conflict"]["type"] == "ts_ml_vs_matchup"
        assert by_match[13]["conflict"]["type"] == "matchup_ml_vs_ts"
        assert by_match[14]["conflict"]["type"] == "none"
        assert by_match[15]["conflict"]["type"] == "incomplete"
        assert by_match[11]["conflict"]["strength"] == pytest.approx(36.67, abs=.01)
        stats = result["statistics"]["conflicts"]
        assert stats["ts_matchup_vs_ml"] == {
            "total": 2, "majority_correct": 0, "dissent_correct": 2,
            "majority_accuracy": 0, "dissent_accuracy": 1,
        }
        assert stats["ts_ml_vs_matchup"]["majority_correct"] == 1
        assert stats["matchup_ml_vs_ts"]["majority_correct"] == 1
        conflicts = await service.history(conflict_only=True)
        assert {item["match_id"] for item in conflicts["items"]} == {11, 12, 13, 16, 17}
        strong = await service.history(strong_conflicts=True)
        assert {item["match_id"] for item in strong["items"]} == {11, 12, 13, 16}
        # Match 16 is future and therefore did not increase the completed total.
        assert strong["statistics"]["conflicts"]["ts_matchup_vs_ml"]["total"] == 1


async def test_official_accuracy_uses_only_two_pre_match_among_ten_retrospective(history_db) -> None:
    async with history_db() as session:
        for index in range(12):
            match_id = 20 + index
            source = "pre_match" if index < 2 else "retrospective"
            actual = 1
            session.add(Match(id=match_id, tournament_id=1, match_date=date(2026, 7, index + 1),
                team_a_id=1, team_b_id=2, format="bo3", stage="group", environment="lan",
                status="completed", resolution_status="resolved", winner_team_id=actual,
                team_a_maps_won=2, team_b_maps_won=0))
            session.add(PredictionHistorySnapshot(match_id=match_id, tournament_id=1,
                as_of=datetime(2026, 6, index + 1, tzinfo=UTC), source=source,
                team_a_id=1, team_b_id=2, team_strength_a=60, team_strength_b=40,
                team_strength_winner_id=1, matchup_a=60, matchup_b=40, matchup_winner_id=1,
                ml_a_probability=.6, ml_b_probability=.4, ml_winner_id=1, actual_winner_id=actual))
        await session.commit()
        result = await PredictionHistoryService(session).history()
        assert result["statistics"]["team_strength"]["total"] == 2
        assert result["statistics"]["matchup"]["total"] == 2
        assert result["statistics"]["ml"]["total"] == 2
        assert result["statistics"]["consensus_3_3"]["total"] == 2
        assert result["statistics"]["snapshot_counts"] == {
            "pre_match": 2, "retrospective": 10, "completed_pre_match": 2,
        }
