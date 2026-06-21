from datetime import datetime, timezone, date
from uuid import UUID

from sqlalchemy import select, or_, and_, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun, DemoBombRoundStat, DemoRoundStat
from cs2eye.services.demo_basic_stats_analyzer import BombRoundStats, RoundStats


async def create_demo_parse_run(
        session: AsyncSession,
        demo_file_path: str,
        artifact_id: str | None = None,
        demo_file_name: str | None = None,
        tournament_name: str | None = None,
        match_date: date | None = None,
        map_name: str | None = None,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
        parser_name: str = "demoparser2",
        map_number: int | None = None,
) -> DemoParseRun:
    parse_run = DemoParseRun(
        demo_file_path=demo_file_path,
        artifact_id=artifact_id,
        demo_file_name=demo_file_name,
        tournament_name=tournament_name,
        match_date=match_date,
        parser_name=parser_name,
        map_name=map_name,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        status="running",
        rounds_count=None,
        error_message=None,
        map_number=map_number,
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


def _get_fallback_round_side_team_names(
        *,
        round_number: int,
        team_a_name: str | None,
        team_b_name: str | None,
) -> tuple[str | None, str | None]:
    """
    Fallback для случаев, когда parser не смог достать реальные CT/T стороны.

    Важно:
    это НЕ основной источник правды.
    Основной источник — round_stat.ct_team_name / round_stat.t_team_name,
    которые пришли из demo parser.

    Здесь остаётся старое предположение:
    - team_a начинает за CT
    - team_b начинает за T
    - после 12 раундов стороны меняются

    Для overtime не угадываем стороны, чтобы не сохранить мусор.
    """

    if team_a_name is None or team_b_name is None:
        return None, None

    if 1 <= round_number <= 12:
        return team_a_name, team_b_name

    if 13 <= round_number <= 24:
        return team_b_name, team_a_name

    return None, None


def _resolve_round_side_team_names(
        *,
        round_stat: RoundStats,
        team_a_name: str | None,
        team_b_name: str | None,
) -> tuple[str | None, str | None]:
    """
    Возвращает реальные CT/T стороны раунда.

    Приоритет:
    1. Данные из parser: round_stat.ct_team_name / round_stat.t_team_name
    2. Fallback по team_a/team_b и номеру раунда
    """

    fallback_ct_team_name, fallback_t_team_name = _get_fallback_round_side_team_names(
        round_number=round_stat.round_number,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
    )

    ct_team_name = round_stat.ct_team_name or fallback_ct_team_name
    t_team_name = round_stat.t_team_name or fallback_t_team_name

    return ct_team_name, t_team_name


def _resolve_round_winner_team_name(
        *,
        round_stat: RoundStats,
        ct_team_name: str | None,
        t_team_name: str | None,
) -> str | None:
    """
    Возвращает победившую команду раунда.

    Приоритет:
    1. winner_team_name из parser
    2. Если его нет — вычисляем по winner_side и CT/T сторонам
    """

    if round_stat.winner_team_name:
        return round_stat.winner_team_name

    if round_stat.winner_side == "CT":
        return ct_team_name

    if round_stat.winner_side == "T":
        return t_team_name

    return None

async def mark_demo_parse_run_success(
        session: AsyncSession,
        parse_run: DemoParseRun,
        demo_file_path: str,
        rounds_count: int,
        bomb_rounds: list[BombRoundStats],
        round_stats: list[RoundStats] | None = None,
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

    round_rows = []

    for round_stat in (round_stats or []):
        ct_team_name, t_team_name = _resolve_round_side_team_names(
            round_stat=round_stat,
            team_a_name=parse_run.team_a_name,
            team_b_name=parse_run.team_b_name,
        )

        winner_team_name = _resolve_round_winner_team_name(
            round_stat=round_stat,
            ct_team_name=ct_team_name,
            t_team_name=t_team_name,
        )

        round_rows.append(
            DemoRoundStat(
                parse_run_id=parse_run.id,
                round_number=round_stat.round_number,
                winner_team_name=winner_team_name,
                winner_side=round_stat.winner_side,
                ct_team_name=ct_team_name,
                t_team_name=t_team_name,
                reason=round_stat.reason,
            )
        )

    session.add_all(round_rows)

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


async def clear_demo_parse_data(session: AsyncSession) -> None:
    await session.execute(
        text("TRUNCATE TABLE demo_parse_runs CASCADE")
    )
    await session.commit()


async def delete_existing_demo_parse_runs(
        *,
        session: AsyncSession,
        tournament_name: str,
        match_date: date,
        map_name: str,
        map_number: int | None,
        team_a_name: str,
        team_b_name: str,
) -> None:
    query = (
        delete(DemoParseRun)
        .where(DemoParseRun.tournament_name == tournament_name)
        .where(DemoParseRun.match_date == match_date)
        .where(DemoParseRun.map_name == map_name)
        .where(
            or_(
                and_(
                    DemoParseRun.team_a_name == team_a_name,
                    DemoParseRun.team_b_name == team_b_name,
                ),
                and_(
                    DemoParseRun.team_a_name == team_b_name,
                    DemoParseRun.team_b_name == team_a_name,
                ),
            )
        )
    )

    if map_number is None:
        query = query.where(DemoParseRun.map_number.is_(None))
    else:
        query = query.where(DemoParseRun.map_number == map_number)

    await session.execute(query)
    await session.commit()

async def get_demo_round_stats(
        session: AsyncSession,
        parse_run_id: UUID,
) -> list[DemoRoundStat]:
    result = await session.execute(
        select(DemoRoundStat)
        .where(DemoRoundStat.parse_run_id == parse_run_id)
        .order_by(DemoRoundStat.round_number.asc())
    )

    return list(result.scalars().all())

async def list_demo_parse_runs(
        *,
        session: AsyncSession,
        limit: int = 50,
        status: str | None = None,
        team_name: str | None = None,
) -> list[DemoParseRun]:
    query = select(DemoParseRun)

    if status is not None:
        query = query.where(DemoParseRun.status == status)

    if team_name is not None:
        normalized_team_name = team_name.strip()

        if normalized_team_name:
            query = query.where(
                or_(
                    DemoParseRun.team_a_name.ilike(f"%{normalized_team_name}%"),
                    DemoParseRun.team_b_name.ilike(f"%{normalized_team_name}%"),
                )
            )

    query = (
        query
        .order_by(DemoParseRun.started_at.desc())
        .limit(limit)
    )

    result = await session.execute(query)

    return list(result.scalars().all())