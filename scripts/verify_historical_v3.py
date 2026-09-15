"""Regression check for historical matchup_v3 support in AnalyticsAsOfService.calculate /
MatchupService.calculate (added because MatchupService used to raise
"historical matchup_v3 requires V3-aware temporal reconstruction (not implemented yet)").

This is a real-data script, not a pytest test: exercising it properly needs the same demo
map/round/kill/damage-event history MapStrengthV3Service and TeamStrengthV3Service read,
which nothing in tests/ seeds (see the comment on
test_matchup_service.py::test_historical_request_delegates_to_v3_aware_reconstruction).
Keep it in the repo and re-run it whenever _matchup_v3, AnalyticsAsOfService.calculate's
matchup_v3 branch, or MatchupService.calculate's historical branch changes.

Checks:
  1) Agreement: for matches spanning different ages (freshest available, ~30 days old,
     ~180 days old), AnalyticsAsOfService.calculate() and MatchupService.calculate() (both
     matchup_v3-only now) must reproduce exactly the score build_dataset_v3's chronological
     loop already computed for that same match. A single
     match cannot catch a systematic date bug (see check 2 below) -- it only proves the
     wiring works for whatever date the one sample happens to use -- so this checks several
     matches of different ages, catching a broader regression in the single-pair reuse.
  2) No date leakage: calculate() replays chronological state up to `as_of`, but
     _matchup_v3 also makes independent MapStrengthV3Service/TeamStrengthV3Service calls
     whose own cutoff must be `as_of` too -- not the resolved match's own match_date, which
     can differ (e.g. a prediction-history capture with an explicit as_of before an
     upcoming, not-yet-played match; see prediction_history_service.capture's non-
     retrospective branch). This calls the same team pair with and without series_id at an
     as_of intentionally earlier than the real match's date, and asserts team_strength (V3-
     service-sourced, not tournament-scoped, so unaffected by form_context's tournament_id)
     is identical either way -- if the resolved match's match_date had leaked in as the V3
     services' cutoff instead of as_of, these would diverge.

Run with: DEBUG=false .venv/bin/python scripts/verify_historical_v3.py
"""
import asyncio
import sys
from datetime import date, timedelta

from cs2eye.db.session import AsyncSessionLocal
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.matchup_service import MatchupService


def pick_by_age(examples, target_age_days):
    today = date.today()
    return min(examples, key=lambda x: abs((today - x.match_date).days - target_age_days))


async def check_agreement(sample, label) -> bool:
    print(f"\n--- {label}: series_id={sample.series_id} date={sample.match_date} "
          f"age={(date.today()-sample.match_date).days}d "
          f"a={sample.team_a_id} b={sample.team_b_id} expected_score={sample.matchup['team_a']['score']}")
    async with AsyncSessionLocal() as session:
        direct = await AnalyticsAsOfService(session).calculate(
            sample.team_a_id, sample.team_b_id, sample.match_date, "bo3", "pre_veto",
            sample.series_id)
    async with AsyncSessionLocal() as session:
        via_service = await MatchupService(session).calculate(
            sample.team_a_id, sample.team_b_id, "bo3", "pre_veto",
            sample.match_date, sample.series_id)
    print(f"  AnalyticsAsOfService.calculate: score={direct['team_a']['score']} reliability={direct['reliability']}")
    print(f"  MatchupService.calculate:       score={via_service['team_a']['score']} reliability={via_service['reliability']}")
    ok = (abs(direct["team_a"]["score"] - sample.matchup["team_a"]["score"]) < 1e-6
          and abs(via_service["team_a"]["score"] - sample.matchup["team_a"]["score"]) < 1e-6
          and direct["model_version"] == "matchup_v3" and via_service["model_version"] == "matchup_v3")
    print(f"  MATCH: {ok}")
    return ok


async def check_no_date_leakage(sample) -> bool:
    earlier = sample.match_date - timedelta(days=10)
    print(f"\n--- date-leakage check: series_id={sample.series_id} real_date={sample.match_date} "
          f"as_of={earlier} (intentionally earlier, series_id still supplied)")
    async with AsyncSessionLocal() as session:
        with_series = await AnalyticsAsOfService(session).calculate(
            sample.team_a_id, sample.team_b_id, earlier, "bo3", "pre_veto",
            sample.series_id)
    async with AsyncSessionLocal() as session:
        without_series = await AnalyticsAsOfService(session).calculate(
            sample.team_a_id, sample.team_b_id, earlier, "bo3", "pre_veto",
            None)
    ta_with, tb_with = with_series["team_strength"]["team_a_score"], with_series["team_strength"]["team_b_score"]
    ta_without, tb_without = without_series["team_strength"]["team_a_score"], without_series["team_strength"]["team_b_score"]
    print(f"  team_strength with series_id:    a={ta_with} b={tb_with}")
    print(f"  team_strength without series_id: a={ta_without} b={tb_without}")
    ok = abs(ta_with - ta_without) < 1e-6 and abs(tb_with - tb_without) < 1e-6
    print(f"  NO LEAKAGE: {ok}")
    if not ok:
        print("  team_strength depends on series_id at a fixed as_of -- the real match's own "
              "match_date is leaking into MapStrengthV3Service/TeamStrengthV3Service's cutoff "
              "instead of the requested as_of.")
    return ok


async def main():
    async with AsyncSessionLocal() as session:
        examples, report = await AnalyticsAsOfService(session).build_dataset_v3("pre_veto")
    print(f"v3 dataset: {report['eligible']} eligible / {report['total_series']} total")

    freshest = max(examples, key=lambda x: x.match_date)
    month_old = pick_by_age(examples, 30)
    half_year_old = pick_by_age(examples, 180)

    results = [
        await check_agreement(freshest, "freshest match"),
        await check_agreement(month_old, "~30 days old"),
        await check_agreement(half_year_old, "~180 days old"),
        await check_no_date_leakage(freshest),
    ]

    print(f"\nALL CHECKS PASSED: {all(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
