from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun, DemoPlayerDamageStat, DemoBombRoundStat
from cs2eye.services.demo_basic_stats_analyzer import PlayerDamageStats, BombRoundStats


async def create_demo_parse_run(
        session: AsyncSession,
        demo_file_path: str,
        parser_name: str = "demoparser2",
) -> DemoParseRun:
    parse_run = DemoParseRun(
        demo_file_path=demo_file_path,
        parser_name=parser_name,
        status="running",
        rounds_count=None,
        error_message=None,
    )

    session.add(parse_run)
    await session.commit()
    await session.refresh(parse_run)

    return parse_run


async def mark_demo_parse_run_success(
        session: AsyncSession,
        parse_run: DemoParseRun,
        demo_file_path: str,
        rounds_count: int,
) -> DemoParseRun:
    parse_run.demo_file_path = demo_file_path
    parse_run.status = "success"
    parse_run.rounds_count = rounds_count
    parse_run.error_message = None
    parse_run.finished_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(parse_run)

    return parse_run


async def mark_demo_parse_run_failed(
        session: AsyncSession,
        parse_run: DemoParseRun,
        error_message: str,
) -> DemoParseRun:
    parse_run.status = "failed"
    parse_run.error_message = error_message
    parse_run.finished_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(parse_run)

    return parse_run


async def mark_demo_parse_run_success_with_player_damage_stats(
        session: AsyncSession,
        parse_run: DemoParseRun,
        demo_file_path: str,
        rounds_count: int,
        players: list[PlayerDamageStats],
        bomb_rounds: list[BombRoundStats],
) -> DemoParseRun:
    parse_run.demo_file_path = demo_file_path
    parse_run.status = "success"
    parse_run.rounds_count = rounds_count
    parse_run.error_message = None
    parse_run.finished_at = datetime.now(timezone.utc)

    player_damage_rows = [
        DemoPlayerDamageStat(
            parse_run_id=parse_run.id,
            player_name=player.player_name,
            team_name=player.team_name,
            total_damage=player.total_damage,
            rounds_count=player.rounds,
            average_damage_per_round=player.average_damage_per_round,
        )
        for player in players
    ]

    bomb_round_rows = [
        DemoBombRoundStat(
            parse_run_id=parse_run.id,
            round_number=bomb_round.round_number,
            planter_name=bomb_round.planter_name,
            planter_team_name=bomb_round.planter_team_name,
            defuser_name=bomb_round.defuser_name,
            defuser_team_name=bomb_round.defuser_team_name,
            outcome=bomb_round.outcome,
            plant_tick=bomb_round.plant_tick,
            defuse_tick=bomb_round.defuse_tick,
            explosion_tick=bomb_round.explosion_tick,
        )
        for bomb_round in bomb_rounds
    ]

    session.add_all(player_damage_rows)
    session.add_all(bomb_round_rows)

    await session.commit()
    await session.refresh(parse_run)

    return parse_run


async def get_demo_bomb_round_stats(
        session: AsyncSession,
        parse_run_id: UUID,
) -> list[DemoBombRoundStat]:
    result = await session.execute(
        select(DemoBombRoundStat)
        .where(DemoBombRoundStat.parse_run_id == parse_run_id)
        .order_by(DemoBombRoundStat.round_number.asc())
    )

    return list(result.scalars().all())