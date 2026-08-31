from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from math import floor
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.he_kill_config import (
    HE_KILL_CONFIDENCE_MODEL_VERSION, HE_KILL_MODEL_VERSION,
)
from cs2eye.models.demo import DemoKill, DemoMapResult
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match
from cs2eye.models.team import Team
from cs2eye.services.he_kill_by_map_service import HEKillByMapService, _normalize_map


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if not count:
        return {
            "predictions_count": 0, "brier_score": None,
            "avg_predicted_probability": None, "actual_he_kill_rate": None,
        }
    probabilities = [float(row["predicted_probability"]) for row in rows]
    labels = [int(bool(row["actual_he_kill"])) for row in rows]
    return {
        "predictions_count": count,
        "brier_score": round(sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / count, 6),
        "avg_predicted_probability": round(sum(probabilities) / count, 6),
        "actual_he_kill_rate": round(sum(labels) / count, 6),
    }


def build_he_kill_backtest_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(10)]
    by_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_confidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        index = min(9, max(0, floor(float(row["predicted_probability"]) * 10)))
        buckets[index].append(row)
        by_map[str(row["map"])].append(row)
        by_confidence[str(row["confidence"])].append(row)
    calibration = []
    for index, items in enumerate(buckets):
        calibration.append({
            "bucket": f"{index * 10}–{(index + 1) * 10}%",
            "lower_bound": index / 10,
            "upper_bound": (index + 1) / 10,
            **_summary(items),
        })
    return {
        "model_version": HE_KILL_MODEL_VERSION,
        "confidence_model_version": HE_KILL_CONFIDENCE_MODEL_VERSION,
        "metrics": _summary(rows),
        "calibration": calibration,
        "by_map": [{"map": name, **_summary(items)} for name, items in sorted(by_map.items())],
        "by_confidence": [
            {"confidence": confidence, **_summary(by_confidence.get(confidence, []))}
            for confidence in ("low", "medium", "high")
        ],
        "predictions": rows,
    }


class HEKillBacktestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self) -> dict[str, Any]:
        candidates = (await self.session.execute(
            select(Match, DemoFile, DemoMapResult)
            .join(DemoFile, DemoFile.match_id == Match.id)
            .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .where(
                Match.status == "completed",
                Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
                DemoMapResult.map_name.is_not(None),
            )
            .order_by(Match.match_date, Match.id, DemoFile.map_number, DemoFile.id)
        )).all()
        # Team B names are loaded once without changing prediction chronology.
        team_ids = {
            team_id for match, _demo, _result in candidates
            for team_id in (match.team_a_id, match.team_b_id) if team_id is not None
        }
        names = dict((await self.session.execute(
            select(Team.id, Team.name).where(Team.id.in_(team_ids))
        )).all()) if team_ids else {}
        grouped: dict[int, list[Any]] = defaultdict(list)
        matches: dict[int, Match] = {}
        for match, demo, result in candidates:
            matches[match.id] = match
            grouped[match.id].append((demo, result))

        rows: list[dict[str, Any]] = []
        production = HEKillByMapService(self.session)
        for series_id, target_maps in grouped.items():
            match = matches[series_id]
            predictions = await production.calculate(
                int(match.team_a_id), int(match.team_b_id),
                as_of=match.match_date, exclude_match_id=series_id,
            )
            prediction_by_map = {item["map"]: item for item in predictions}
            labels = await self._actual_labels([demo.id for demo, _ in target_maps])
            as_of = datetime.combine(match.match_date, datetime.min.time(), tzinfo=UTC)
            for demo, result in target_maps:
                map_name = _normalize_map(result.map_name)
                prediction = prediction_by_map.get(map_name or "")
                if prediction is None:
                    continue
                rows.append({
                    "series_id": series_id,
                    "map": map_name,
                    "as_of": as_of.isoformat(),
                    "team_a": {"id": match.team_a_id, "name": names.get(match.team_a_id)},
                    "team_b": {"id": match.team_b_id, "name": names.get(match.team_b_id)},
                    "predicted_probability": prediction["probability"],
                    "confidence": prediction["confidence"],
                    "team_a_sample": prediction["team_a_sample"],
                    "team_b_sample": prediction["team_b_sample"],
                    "actual_he_kill": labels.get(demo.id, False),
                })
        return build_he_kill_backtest_report(rows)

    async def _actual_labels(self, demo_ids: list[int]) -> dict[int, bool]:
        labels = {demo_id: False for demo_id in demo_ids}
        if not demo_ids:
            return labels
        kills = list((await self.session.scalars(
            select(DemoKill).where(DemoKill.demo_file_id.in_(demo_ids))
        )).all())
        for kill in kills:
            if HEKillByMapService._valid_he_kill(kill):
                labels[kill.demo_file_id] = True
        return labels


__all__ = ["HEKillBacktestService", "build_he_kill_backtest_report"]
