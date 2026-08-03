from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.core.config import settings
from cs2eye.db.base import Base
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, RankingImportRun, Team, TeamRankingSnapshot
from cs2eye.services.opponent_rank_reclassify_service import (
    OpponentRankReclassifyService,
)
from cs2eye.services.opponent_rank_resolver import resolve_opponent_rank
from cs2eye.services.player_internal_rating_service import INTERNAL_RATING_VERSION


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def add_team(session: AsyncSession, rank: int | None = 22) -> Team:
    team = Team(bo3_id=1, bo3_slug="navi", name="NAVI", current_rank=rank)
    session.add(team)
    await session.flush()
    return team


async def add_snapshot(
    session: AsyncSession,
    team: Team,
    day: date,
    rank: int,
) -> TeamRankingSnapshot:
    run = RankingImportRun(status="succeeded", source_url="https://bo3.test")
    session.add(run)
    await session.flush()
    snapshot = TeamRankingSnapshot(
        import_run_id=run.id,
        team_id=team.id,
        source="bo3",
        ranking_date=day,
        rank=rank,
        points=Decimal("1000"),
        roster_payload=[],
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


@pytest.mark.parametrize(
    ("rank", "group"),
    [(1, "top_15"), (15, "top_15"), (16, "top_16_30"),
     (30, "top_16_30"), (31, "outside_top_30")],
)
async def test_snapshot_rank_boundaries(
    session: AsyncSession, rank: int, group: str,
) -> None:
    match_date = date(2026, 5, 10)
    team = await add_team(session)
    snapshot = await add_snapshot(session, team, match_date, rank)

    result = await resolve_opponent_rank(session, team.id, match_date)

    assert result.rank == rank
    assert result.rank_group == group
    assert result.source == "historical_snapshot"
    assert result.snapshot_id == snapshot.id
    assert result.snapshot_date == match_date


async def test_latest_snapshot_not_after_match_is_used(session: AsyncSession) -> None:
    team = await add_team(session, rank=25)
    await add_snapshot(session, team, date(2026, 5, 1), 5)
    expected = await add_snapshot(session, team, date(2026, 5, 8), 7)
    await add_snapshot(session, team, date(2026, 5, 15), 18)

    result = await resolve_opponent_rank(session, team.id, date(2026, 5, 10))

    assert result.rank == 7
    assert result.snapshot_id == expected.id
    assert result.snapshot_date == date(2026, 5, 8)


async def test_old_snapshot_uses_current_fallback(session: AsyncSession) -> None:
    match_date = date(2026, 5, 20)
    team = await add_team(session, rank=16)
    await add_snapshot(
        session,
        team,
        match_date - timedelta(days=settings.max_ranking_snapshot_age_days + 1),
        4,
    )

    result = await resolve_opponent_rank(session, team.id, match_date)

    assert result.rank == 16
    assert result.rank_group == "top_16_30"
    assert result.source == "current_fallback"
    assert result.snapshot_id is None
    assert result.snapshot_date is None


async def test_snapshot_at_age_limit_is_used(session: AsyncSession) -> None:
    match_date = date(2026, 5, 20)
    team = await add_team(session)
    snapshot = await add_snapshot(
        session,
        team,
        match_date - timedelta(days=settings.max_ranking_snapshot_age_days),
        9,
    )
    result = await resolve_opponent_rank(session, team.id, match_date)
    assert result.source == "historical_snapshot"
    assert result.snapshot_id == snapshot.id


async def test_missing_match_date_uses_current_fallback(session: AsyncSession) -> None:
    team = await add_team(session, rank=31)
    result = await resolve_opponent_rank(session, team.id, None)
    assert (result.rank, result.rank_group, result.source) == (
        31, "outside_top_30", "current_fallback",
    )


async def test_missing_team_or_rank_is_unknown(session: AsyncSession) -> None:
    assert (await resolve_opponent_rank(session, None, date(2026, 1, 1))).source == "unknown"
    team = await add_team(session, rank=None)
    result = await resolve_opponent_rank(session, team.id, date(2026, 1, 1))
    assert result.rank is None
    assert result.rank_group == "unknown"
    assert result.source == "unknown"


async def test_reclassify_changes_only_rank_fields_and_recalculates_player(
    session: AsyncSession,
) -> None:
    match_date = date(2026, 5, 10)
    opponent = await add_team(session, rank=22)
    snapshot = await add_snapshot(session, opponent, date(2026, 5, 8), 7)
    player = Player(bo3_id=2, bo3_slug="player", nickname="Player")
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=match_date,
        original_filename="map.dem", storage_path="map.dem",
        file_size_bytes=1, sha256="a" * 64,
    )
    session.add_all([player, demo])
    await session.flush()
    run = DemoParseRun(
        demo_file_id=demo.id, status="success",
        parser_name="test", parser_version="1",
    )
    session.add(run)
    await session.flush()
    stat = DemoPlayerStat(
        demo_file_id=demo.id, parse_run_id=run.id, player_id=player.id,
        steam_id="2", identity_key="steam:2", nickname="Player",
        team_name="Other", opponent_team_id=opponent.id,
        opponent_team_name="NAVI", opponent_rank=22,
        opponent_rank_group="top_16_30",
        opponent_rank_source="current_fallback",
        rounds_played=20, kills=10, deaths=5, assists=3,
        total_damage=1600, adr=Decimal("80"), kast_rounds=15,
        kast_percent=Decimal("75"), internal_rating=Decimal("7.2000"),
        internal_rating_version=INTERNAL_RATING_VERSION,
    )
    session.add(stat)
    await session.commit()
    gameplay_before = (
        stat.kills, stat.deaths, stat.assists, stat.adr,
        stat.kast_percent, stat.internal_rating,
    )

    result = await OpponentRankReclassifyService(session).reclassify_one(demo.id)

    assert result is not None
    assert result.updated_count == 1
    assert result.players_recalculated == 1
    assert stat.opponent_rank == 7
    assert stat.opponent_rank_group == "top_15"
    assert stat.opponent_rank_source == "historical_snapshot"
    assert stat.opponent_rank_snapshot_id == snapshot.id
    assert stat.opponent_rank_snapshot_date == date(2026, 5, 8)
    assert gameplay_before == (
        stat.kills, stat.deaths, stat.assists, stat.adr,
        stat.kast_percent, stat.internal_rating,
    )
    assert player.internal_rating_top15 == Decimal("7.2000")
    assert player.internal_rating_top16_30 is None
