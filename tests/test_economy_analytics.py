from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.analytics.economy.config import classify_economy
from cs2eye.db.base import Base
from cs2eye.models.demo import DemoMapResult, DemoRound, DemoTeamEconomyStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.demo_round_service import (
    ParsedRound, economy_data_status, normalize_rounds,
    recalculate_demo_team_economy_stats,
)


def result(score_a=1, score_b=0):
    return DemoMapResult(
        id=1, demo_file_id=1, map_name="nuke", team_a_name="A", team_b_name="B",
        team_a_score=score_a, team_b_score=score_b, rounds_count=score_a + score_b,
        result_source="demo_parser", metadata_status="complete",
    )


def parsed(*, scores, winner=2, t="A", ct="B", warmup=False, restart=False,
           t_value=20_000, ct_value=22_000):
    return ParsedRound(
        raw_round_index=sum(scores.values()) - 1, winner_side=winner,
        t_team_name=t, ct_team_name=ct, raw_scores_after=scores,
        is_warmup=warmup, is_restart=restart,
        t_equipment_value=t_value, ct_equipment_value=ct_value,
    )


def test_pistol_detection_uses_normalized_gameplay_rounds() -> None:
    rows = [
        parsed(scores={"A": 1, "B": 0}, warmup=True),
        parsed(scores={"A": 1, "B": 0}, restart=True),
        parsed(scores={"A": 1, "B": 0}),
    ]
    rounds, warnings = normalize_rounds(rows, result())
    assert len(rounds) == 1
    assert rounds[0].is_pistol_round is True
    assert rounds[0].pistol_round_number == 1
    assert "warmup_round_skipped" in warnings and "restart_round_skipped" in warnings


def test_second_pistol_and_overtime() -> None:
    second, _ = normalize_rounds([
        parsed(scores={"A": 7, "B": 6}, winner=3, t="B", ct="A"),
    ], result(7, 6))
    assert second[0].round_number == 13
    assert second[0].pistol_round_number == 2
    overtime, _ = normalize_rounds([
        parsed(scores={"A": 13, "B": 12}),
    ], result(13, 12))
    assert overtime[0].phase == "overtime"
    assert overtime[0].is_pistol_round is False


@pytest.mark.parametrize(("value", "side", "expected"), [
    (3_000, "T", "eco"), (10_000, "T", "force_buy"),
    (18_000, "T", "full_buy"), (19_999, "CT", "force_buy"),
    (20_000, "CT", "full_buy"), (None, "T", "unknown"),
])
def test_economy_classification(value, side, expected) -> None:
    assert classify_economy(value, side) == expected


def test_unknown_round_makes_status_partial() -> None:
    rounds, _ = normalize_rounds([
        parsed(scores={"A": 1, "B": 0}, t_value=None),
    ], result())
    status, warnings = economy_data_status(rounds, "complete")
    assert status == "partial"
    assert warnings == ["economy_unknown_rounds:1"]


def test_split_boundary_unknown_is_excluded_without_invalidating_map() -> None:
    rounds, _ = normalize_rounds([
        parsed(scores={"A": 1, "B": 0}, t_value=None),
        parsed(scores={"A": 2, "B": 0}, t_value=18_000, ct_value=20_000),
    ], result(2, 0))
    status, warnings = economy_data_status(rounds, "complete")
    assert status == "complete"
    assert warnings == []
    assert rounds[0].team_a_economy == "unknown"
    assert rounds[1].team_a_economy == "full_buy"


async def test_conversion_comeback_and_matchup_economy_are_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(DemoFile(
            id=1, tournament_name="Кубок", tournament_slug="cup", match_date=date(2026, 8, 10),
            original_filename="map.dem", storage_path="map.dem", file_size_bytes=1, sha256="e" * 64,
        ))
        map_result = result(2, 2)
        map_result.economy_data_status = "complete"
        session.add(map_result)
        session.add_all([
            # A wins pistol, then converts against B force-buy.
            DemoRound(demo_file_id=1, demo_map_result_id=1, round_number=1, phase="regulation", half="first_half", team_a_side="T", team_b_side="CT", winner_team_name="A", winner_side="T", end_reason="cts_eliminated", is_complete=True, is_pistol_round=True, pistol_round_number=1, team_a_economy="eco", team_b_economy="eco"),
            DemoRound(demo_file_id=1, demo_map_result_id=1, round_number=2, phase="regulation", half="first_half", team_a_side="T", team_b_side="CT", winner_team_name="A", winner_side="T", end_reason="cts_eliminated", is_complete=True, team_a_economy="full_buy", team_b_economy="force_buy"),
            # B wins second pistol, A steals the following force-vs-full round.
            DemoRound(demo_file_id=1, demo_map_result_id=1, round_number=13, phase="regulation", half="second_half", team_a_side="CT", team_b_side="T", winner_team_name="B", winner_side="T", end_reason="cts_eliminated", is_complete=True, is_pistol_round=True, pistol_round_number=2, team_a_economy="eco", team_b_economy="eco"),
            DemoRound(demo_file_id=1, demo_map_result_id=1, round_number=14, phase="regulation", half="second_half", team_a_side="CT", team_b_side="T", winner_team_name="A", winner_side="CT", end_reason="terrorists_eliminated", is_complete=True, team_a_economy="force_buy", team_b_economy="full_buy"),
        ])
        await session.flush()
        first = await recalculate_demo_team_economy_stats(session, map_result)
        await session.flush()
        second = await recalculate_demo_team_economy_stats(session, map_result)
        await session.flush()
        assert len(first) == len(second) == 2
        a = next(item for item in second if item.team_name == "A")
        assert a.pistol_conversion_opportunities == a.pistol_conversions == 1
        assert a.post_pistol_vs_force_rounds == a.post_pistol_vs_force_wins == 1
        assert a.second_round_comeback_opportunities == a.second_round_comeback_wins == 1
        assert a.force_vs_full_buy_rounds == a.force_vs_full_buy_wins == 1
        assert len((await session.execute(__import__("sqlalchemy").select(DemoTeamEconomyStat))).scalars().all()) == 2
    await engine.dispose()
