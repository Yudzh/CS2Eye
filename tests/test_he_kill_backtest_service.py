from datetime import timedelta

from cs2eye.services.he_kill_backtest_service import (
    HEKillBacktestService, build_he_kill_backtest_report,
)
from cs2eye.services.he_kill_by_map_service import HEKillByMapService
from tests.test_he_kill_by_map_service import AS_OF, add_map, he_db


def row(probability: float, actual: bool, *, map_name: str = "ancient", confidence: str = "low") -> dict:
    return {
        "predicted_probability": probability, "actual_he_kill": actual,
        "map": map_name, "confidence": confidence,
    }


def test_backtest_metrics_and_breakdowns() -> None:
    report = build_he_kill_backtest_report([
        row(.2, False, map_name="ancient", confidence="low"),
        row(.8, True, map_name="ancient", confidence="high"),
        row(.6, False, map_name="mirage", confidence="medium"),
    ])
    assert report["metrics"] == {
        "predictions_count": 3, "brier_score": .146667,
        "avg_predicted_probability": .533333, "actual_he_kill_rate": .333333,
    }
    assert {item["map"]: item["predictions_count"] for item in report["by_map"]} == {
        "ancient": 2, "mirage": 1,
    }
    assert [item["predictions_count"] for item in report["by_confidence"]] == [1, 1, 1]


def test_calibration_has_all_buckets_including_empty() -> None:
    report = build_he_kill_backtest_report([row(0, False), row(.1, True), row(1, True)])
    buckets = report["calibration"]
    assert len(buckets) == 10
    assert buckets[0]["predictions_count"] == 1
    assert buckets[1]["predictions_count"] == 1
    assert buckets[5]["predictions_count"] == 0
    assert buckets[5]["avg_predicted_probability"] is None
    assert buckets[9]["predictions_count"] == 1


async def test_actual_label_accepts_only_valid_he_kill(he_db) -> None:
    async with he_db() as session:
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=1), kills=[{}])
        await add_map(session, 2, "mirage", AS_OF - timedelta(days=1), kills=[{"is_teamkill": True}])
        await session.commit()
        labels = await HEKillBacktestService(session)._actual_labels([1, 2])
    assert labels == {1: True, 2: False}


async def test_backtest_calls_production_before_loading_label_and_excludes_target(he_db, monkeypatch) -> None:
    from cs2eye.models.match import Match

    async with he_db() as session:
        session.add(Match(
            id=50, match_date=AS_OF - timedelta(days=1), team_a_id=1, team_b_id=2,
            format="bo1", status="completed", resolution_status="resolved",
            winner_team_id=1,
        )); await session.flush()
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=1), match_id=50, kills=[{}])
        await session.commit()
        predicted = False
        calls = []

        async def calculate(self, a, b, *, as_of, exclude_match_id=None):
            nonlocal predicted
            predicted = True
            calls.append((a, b, as_of, exclude_match_id))
            return [{
                "map": "ancient", "probability": .42, "confidence": "low",
                "team_a_sample": 0, "team_b_sample": 0,
            }]

        original_labels = HEKillBacktestService._actual_labels
        async def labels(self, demo_ids):
            assert predicted, "target label was loaded before prediction"
            return await original_labels(self, demo_ids)

        monkeypatch.setattr(HEKillByMapService, "calculate", calculate)
        monkeypatch.setattr(HEKillBacktestService, "_actual_labels", labels)
        report = await HEKillBacktestService(session).run()

    assert calls == [(1, 2, AS_OF - timedelta(days=1), 50)]
    prediction = report["predictions"][0]
    assert prediction["as_of"].startswith((AS_OF - timedelta(days=1)).isoformat())
    assert prediction["actual_he_kill"] is True
    assert prediction["predicted_probability"] == .42
    assert prediction["team_a_sample"] == prediction["team_b_sample"] == 0


async def test_historical_reconstruction_cannot_see_target_or_future_series(he_db) -> None:
    from cs2eye.models.match import Match

    async with he_db() as session:
        session.add_all([
            Match(id=50, match_date=AS_OF - timedelta(days=2), team_a_id=1, team_b_id=2,
                  format="bo1", status="completed", resolution_status="resolved", winner_team_id=1),
            Match(id=51, match_date=AS_OF - timedelta(days=1), team_a_id=1, team_b_id=2,
                  format="bo1", status="completed", resolution_status="resolved", winner_team_id=2),
        ]); await session.flush()
        await add_map(session, 1, "ancient", AS_OF - timedelta(days=2), match_id=50, kills=[])
        await add_map(session, 2, "ancient", AS_OF - timedelta(days=1), match_id=51, kills=[{}])
        await session.commit()
        report = await HEKillBacktestService(session).run()
    rows = {item["series_id"]: item for item in report["predictions"]}
    assert rows[50]["team_a_sample"] == rows[50]["team_b_sample"] == 0
    assert rows[51]["team_a_sample"] == rows[51]["team_b_sample"] == 1
    assert rows[50]["actual_he_kill"] is False
    assert rows[51]["actual_he_kill"] is True
