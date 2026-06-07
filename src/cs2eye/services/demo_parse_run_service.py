from datetime import datetime, timezone, date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun, DemoBombRoundStat
from cs2eye.services.demo_basic_stats_analyzer import BombRoundStats


async def create_demo_parse_run(
        session: AsyncSession,
        demo_file_path: str,
        tournament_name: str | None = None,
        match_date: date | None = None,
        map_name: str | None = None,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
        parser_name: str = "demoparser2",
) -> DemoParseRun:
    parse_run = DemoParseRun(
        demo_file_path=demo_file_path,
        tournament_name=tournament_name,
        match_date=match_date,
        parser_name=parser_name,
        map_name=map_name,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        status="running",
        rounds_count=None,
        error_message=None,
    )

    session.add(parse_run)
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


async def mark_demo_parse_run_success(
        session: AsyncSession,
        parse_run: DemoParseRun,
        demo_file_path: str,
        rounds_count: int,
        bomb_rounds: list[BombRoundStats],
) -> DemoParseRun:
    parse_run.demo_file_path = demo_file_path
    parse_run.status = "success"
    parse_run.rounds_count = rounds_count
    parse_run.error_message = None
    parse_run.finished_at = datetime.now(timezone.utc)

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