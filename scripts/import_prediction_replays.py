"""Import saved historical evaluations for the results page; never label them pre-match.

DEBUG=false .venv/bin/python scripts/import_prediction_replays.py FILE [FILE ...]
Each JSON file is a list of rows with id (match ID), date, features, v12/v13 probabilities.
Imports are idempotent; existing saved predictions are never overwritten.
"""
import argparse
import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match
from cs2eye.models.prediction import MatchPrediction, WinProbabilityModelArtifact


async def import_replays(paths: list[Path]) -> int:
    created = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():
            models = {row.model_version: row for row in (await session.scalars(
                select(WinProbabilityModelArtifact))).all()}
            for path in paths:
                for row in json.loads(path.read_text()):
                    match = await session.get(Match, row["id"])
                    if match is None or match.match_date != date.fromisoformat(row["date"]):
                        raise ValueError(f"Match/date mismatch: {row['id']}")
                    # Historical diagnostics preserve orientation in the matchup payload.
                    context = row.get("context")
                    if context:
                        a, b = context["team_a"]["id"], context["team_b"]["id"]
                    else:
                        a, b = match.team_a_id, match.team_b_id
                    if {a, b} != {match.team_a_id, match.team_b_id}:
                        raise ValueError(f"Match participants changed: {match.id}")
                    for version in ("v12", "v13"):
                        probability = Decimal(str(row[version]))
                        if not 0 <= probability <= 1:
                            raise ValueError("Invalid probability")
                        existing = await session.scalar(select(MatchPrediction.id).where(
                            MatchPrediction.series_id == match.id,
                            MatchPrediction.mode == "pre_veto",
                            MatchPrediction.model_version == version,
                            MatchPrediction.as_of == match.match_date))
                        if existing is not None:
                            continue
                        artifact = models[version]
                        session.add(MatchPrediction(
                            series_id=match.id, as_of=match.match_date, mode="pre_veto",
                            source="historical_replay", model_version=version,
                            feature_schema_version=artifact.feature_schema_version,
                            team_a_id=a, team_b_id=b, team_a_probability=probability,
                            team_b_probability=1-probability, confidence=max(probability,1-probability),
                            feature_snapshot={"features": row["features"], "basis": "historical_replay",
                                              "import_file": path.name, "strictly_before_match_date": True},
                            prediction_status="available"))
                        await session.flush()
                        created += 1
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    print(f"Imported {asyncio.run(import_replays(args.paths))} historical predictions.")
