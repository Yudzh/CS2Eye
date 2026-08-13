from datetime import UTC, datetime
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.team import Player


FOUR_PLACES = Decimal("0.0001")
INTERNAL_RATING_VERSION = "v1"
KILLS_WEIGHT = Decimal("0.35")
ASSISTS_WEIGHT = Decimal("0.10")
SURVIVAL_WEIGHT = Decimal("0.20")
ADR_WEIGHT = Decimal("0.20")
KAST_WEIGHT = Decimal("0.15")
RATING_SCALE = Decimal("10")


@dataclass(frozen=True)
class RatingSample:
    rating: Decimal | None
    maps_count: int
    rounds_count: int


@dataclass(frozen=True)
class PlayerInternalRatings:
    overall: RatingSample
    top15: RatingSample
    top16_30: RatingSample


def calculate_internal_rating(
    *, rounds_played: int, kills: int, deaths: int, assists: int,
    adr: Decimal, kast_percent: Decimal,
) -> Decimal:
    if rounds_played <= 0:
        return Decimal("0.0000")
    rounds = Decimal(rounds_played)
    raw = (
        KILLS_WEIGHT * Decimal(kills) / rounds
        + ASSISTS_WEIGHT * Decimal(assists) / rounds
        + SURVIVAL_WEIGHT * (Decimal(1) - Decimal(deaths) / rounds)
        + ADR_WEIGHT * adr / Decimal(100)
        + KAST_WEIGHT * kast_percent / Decimal(100)
    )
    scaled = raw * RATING_SCALE
    return max(Decimal(0), min(Decimal(10), scaled)).quantize(
        FOUR_PLACES, rounding=ROUND_HALF_UP,
    )


def calculate_rating_sample(
    rows: list[tuple[int, Decimal, int, str]], group: str | None = None,
) -> RatingSample:
    selected = [row for row in rows if group is None or row[3] == group]
    rounds = sum(row[2] for row in selected)
    if rounds <= 0:
        return RatingSample(None, 0, 0)
    weighted = sum((Decimal(row[1]) * row[2] for row in selected), Decimal(0))
    return RatingSample(
        (weighted / rounds).quantize(FOUR_PLACES),
        len({row[0] for row in selected}), rounds,
    )


async def recalculate_player_internal_ratings(
    session: AsyncSession, player_id: int, *, commit: bool = True,
) -> PlayerInternalRatings | None:
    player = await session.get(Player, player_id)
    if player is None:
        return None
    rows = (
        await session.execute(
            select(
                DemoPlayerStat.demo_file_id,
                DemoPlayerStat.internal_rating,
                DemoPlayerStat.rounds_played,
                DemoPlayerStat.opponent_rank_group,
            ).join(
                DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id,
            ).where(
                DemoPlayerStat.player_id == player_id,
                DemoPlayerStat.rounds_played > 0,
                DemoPlayerStat.internal_rating_version == INTERNAL_RATING_VERSION,
                DemoParseRun.status == "success",
            )
        )
    ).all()
    ratings = PlayerInternalRatings(
        overall=calculate_rating_sample(rows),
        top15=calculate_rating_sample(rows, "top_15"),
        top16_30=calculate_rating_sample(rows, "top_16_30"),
    )
    player.internal_rating = ratings.overall.rating
    player.internal_rating_maps_count = ratings.overall.maps_count
    player.internal_rating_rounds_count = ratings.overall.rounds_count
    player.internal_rating_top15 = ratings.top15.rating
    player.internal_rating_top15_maps_count = ratings.top15.maps_count
    player.internal_rating_top15_rounds_count = ratings.top15.rounds_count
    player.internal_rating_top16_30 = ratings.top16_30.rating
    player.internal_rating_top16_30_maps_count = ratings.top16_30.maps_count
    player.internal_rating_top16_30_rounds_count = ratings.top16_30.rounds_count
    player.internal_rating_version = (
        INTERNAL_RATING_VERSION if ratings.overall.rounds_count else None
    )
    player.internal_rating_updated_at = datetime.now(UTC)
    # Keep the persisted compatibility score in sync with the V2 inputs.
    from cs2eye.services.player_service import calculate_player_strength_for_player
    player.player_strength, player.strength_breakdown = calculate_player_strength_for_player(player)
    if commit:
        await session.commit()
    return ratings


async def recalculate_player_internal_rating(
    session: AsyncSession, player_id: int, *, commit: bool = True,
) -> None:
    await recalculate_player_internal_ratings(
        session, player_id, commit=commit,
    )


async def recalculate_players_internal_rating(
    session: AsyncSession, player_ids: set[int],
) -> int:
    for player_id in player_ids:
        await recalculate_player_internal_ratings(session, player_id, commit=False)
    if player_ids:
        await session.commit()
    return len(player_ids)
