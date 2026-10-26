"""Prepare server-side forecasts before making a release available to the bot."""
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import or_, select

from cs2eye.db.session import AsyncSessionLocal, engine
from cs2eye.models.match import Match
from cs2eye.services.prediction_history_service import PredictionHistoryService
from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder


async def prepare_forecasts(factory=AsyncSessionLocal, *, now=None):
    now = now or datetime.now(UTC)
    # Include today's known pairs even when kickoff has passed: missing original
    # forecasts must be reported, never silently manufactured after kickoff.
    async with factory() as session:
        query = select(Match.id).where(
            Match.status == "scheduled", Match.winner_team_id.is_(None),
            Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
            or_(Match.starts_at >= now, Match.match_date >= now.date()),
        ).order_by(Match.starts_at.asc().nulls_last(), Match.id)
        ids = list((await session.scalars(query)).all())
    report = {"checked": len(ids), "available": [], "retrospective": [], "errors": []}
    for match_id in ids:
        try:
            async with factory() as session:
                match = await session.get(Match, match_id)
                try:
                    PredictionHistoryService.ensure_before_start(match)
                except ValueError:
                    card = await MatchAnalysisContextBuilder(session).build_card(match_id, include_retrospective=True)
                    if card["prediction"].get("source") == "retrospective" and card["prediction"]["status"] == "available":
                        report["retrospective"].append(match_id)
                        continue
                snapshot = await PredictionHistoryService(session).capture(match_id)
                if (snapshot.source != "pre_match" or snapshot.ml_model_version is None
                        or snapshot.ml_a_probability is None or snapshot.ml_b_probability is None
                        or not 0 <= snapshot.ml_a_probability <= 1
                        or not 0 <= snapshot.ml_b_probability <= 1
                        or abs(snapshot.ml_a_probability + snapshot.ml_b_probability - 1) > 0.000001):
                    raise ValueError("Saved forecast has no valid model probabilities")
                await session.commit()
                report["available"].append(match_id)
        except Exception as error:
            # Keep already prepared matches; fail the release on any missing one.
            report["errors"].append({"match_id": match_id, "error": type(error).__name__,
                                     "message": str(error) if isinstance(error, (ValueError, LookupError))
                                     else "Forecast preparation failed; inspect server logs"})
    return report


async def main():
    try:
        from cs2eye.deployment.player_steam_aliases import prepare as prepare_player_aliases
        aliases = await prepare_player_aliases(AsyncSessionLocal)
        print("Player account readiness: " + json.dumps(aliases), flush=True)
        from cs2eye.deployment.rosters import verify_rosters
        roster_report = await verify_rosters(AsyncSessionLocal)
        print("Roster readiness: " + json.dumps(roster_report), flush=True)
        if roster_report['errors']:
            raise SystemExit("Deployment incomplete: PandaScore roster identities are inconsistent")
        report = await prepare_forecasts()
        print("Forecast readiness: " + json.dumps(report, ensure_ascii=False), flush=True)
        if report["errors"]:
            raise SystemExit("Deployment incomplete: some match forecasts are unavailable")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
