from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.integrations.bo3.client import Bo3Client
from cs2eye.integrations.bo3.client import Bo3PlayerResponse
from cs2eye.models.team import Player, Team, TeamParticipantMembership
from cs2eye.models.demo import DemoMapResult, DemoParseRun, DemoPlayerStat
from cs2eye.services.demo_utility_service import COUNT_KEYS, _base as utility_base, finalize as finalize_utility
from cs2eye.models.demo_file import DemoFile
from cs2eye.analytics.scoring.config import (
    NORMALIZATION_RULES, PLAYER_STRENGTH_MODEL_VERSION, PLAYER_WEIGHTS, normalize,
)
from cs2eye.analytics.scoring.core import FactorInput, sample_reliability, score_factors
from cs2eye.services.round_swing_service import player_round_swing


@dataclass(frozen=True)
class PlayerTeamStatus:
    team: Team
    is_active: bool
    participant_type: str


def calculate_player_strength(
    rating: Decimal | None = None, *, internal_rating: Decimal | None = None,
    internal_maps: int = 0, top15_rating: Decimal | None = None,
    top15_maps: int = 0, top16_30_rating: Decimal | None = None,
    top16_30_maps: int = 0, recent_rating: Decimal | None = None,
    recent_maps: int = 0, role: str | None = None,
    round_swing_score: float | None = None, round_swing_rounds: int = 0,
    round_swing_confidence: float | None = None,
) -> tuple[int | None, dict | None]:
    """Сила игрока V2: отсутствие данных нейтрально и никогда не равно нулю."""
    if rating is None and internal_rating is None:
        return None, None

    def rating_factor(key: str, label: str, value: Decimal | None, weight: float,
                      sample: int | None, reason: str) -> FactorInput:
        confidence = sample_reliability(sample, 5) if sample is not None else .65
        score = normalize(float(value), "internal_rating") if value is not None else None
        if score is not None and sample is not None:
            score = 50 + (score - 50) * confidence
        return FactorInput(
            key, label, float(value) if value is not None else None, score, weight,
            sample, confidence if value is not None else 0.0, reason,
            available=value is not None, reference_value=50,
            reference_source="нейтральная линия внутреннего рейтинга; стягивание с учётом числа карт",
        )

    factors = [
        rating_factor("internal_rating", "Общий внутренний рейтинг", internal_rating,
                      PLAYER_WEIGHTS["internal_rating"], internal_maps,
                      "Внутренний рейтинг v1 по демо: убийства за раунд 35%, помощи за раунд 10%, выживаемость 20%, ADR 20%, KAST 15%."),
        FactorInput(
            "bo3_rating", "Рейтинг BO3.gg", float(rating) if rating is not None else None,
            normalize(float(rating), "bo3_rating") if rating is not None else None,
            PLAYER_WEIGHTS["bo3_rating"], None, .65 if rating is not None else 0.0,
            "Внешняя базовая оценка BO3.gg за шесть месяцев; временная экспертная нормализация 4/6/8.",
            rating is not None,
        ),
        FactorInput(
            "round_swing", "Round Swing", round_swing_score, round_swing_score,
            PLAYER_WEIGHTS["round_swing"], round_swing_rounds,
            round_swing_confidence or 0.0,
            "Adjusted Swing/round, robust-normalized on the historical player distribution; contextual subsets are explanations only.",
            round_swing_score is not None,
        ),
        rating_factor("top15_performance", "Игра против Top 1–15", top15_rating,
                      PLAYER_WEIGHTS["top15_performance"], top15_maps,
                      "Внутренний рейтинг против соперников, исторически отнесённых к Top 1–15."),
        rating_factor("top16_30_performance", "Игра против Top 16–30", top16_30_rating,
                      PLAYER_WEIGHTS["top16_30_performance"], top16_30_maps,
                      "Внутренний рейтинг против соперников, исторически отнесённых к Top 16–30."),
    ]
    if recent_rating is not None and internal_rating is not None:
        delta = float(recent_rating - internal_rating)
        factors.append(FactorInput(
            "recent_form", "Текущая форма", delta, normalize(delta, "rating_delta"),
            PLAYER_WEIGHTS["recent_form"], recent_maps,
            sample_reliability(recent_maps, 5),
            "Внутренний рейтинг на последних картах относительно общего уровня игрока.",
            True, 0.0, "общий внутренний рейтинг игрока",
        ))
    else:
        factors.append(FactorInput(
            "recent_form", "Текущая форма", None, None, PLAYER_WEIGHTS["recent_form"],
            None, 0.0, "Нет совместимой выборки последних демо.", False,
        ))
    # Текущих данных о ролях недостаточно для достоверной профильной оценки.
    factors.append(FactorInput(
        "role_performance", "Эффективность в роли", role, None,
        PLAYER_WEIGHTS["role_performance"], None, 0.0,
        "Для оценки роли нужны первые дуэли, размены, гранаты и полные AWP-события; отсутствие метаданных не является штрафом.",
        False,
    ))
    available_confidences = [f.confidence for f in factors if f.available and f.confidence is not None]
    reliability = sum(available_confidences) / len(available_confidences) if available_confidences else 0.0
    result = score_factors(factors, reliability)
    payload = {
        "model_version": PLAYER_STRENGTH_MODEL_VERSION, "raw_score": result.raw_score,
        "reliability": result.reliability,
        "confidence_adjustment": result.confidence_adjustment,
        "final_score": result.final_score,
        "normalization_source": NORMALIZATION_RULES["internal_rating"].source,
        "factors": [factor.__dict__ for factor in result.factors],
    }
    return round(result.final_score), payload


def calculate_player_strength_for_player(player: Player, *, role: str | None = None):
    return calculate_player_strength(
        player.bo3_rating, internal_rating=player.internal_rating,
        internal_maps=player.internal_rating_maps_count,
        top15_rating=player.internal_rating_top15,
        top15_maps=player.internal_rating_top15_maps_count,
        top16_30_rating=player.internal_rating_top16_30,
        top16_30_maps=player.internal_rating_top16_30_maps_count, role=role,
    )


def apply_player_profile(player: Player, profile: Bo3PlayerResponse, synced_at: datetime) -> None:
    player.bo3_rating = profile.six_month_avg_rating
    strength, breakdown = calculate_player_strength_for_player(player)
    player.bo3_slug = profile.slug
    player.nickname = profile.nickname
    player.first_name = profile.first_name
    player.last_name = profile.last_name
    player.image_url = profile.image_url
    player.country_code = profile.country.code if profile.country else None
    player.country_name = profile.country.name if profile.country else None
    player.player_strength = strength
    player.strength_breakdown = breakdown
    player.source_updated_at = profile.updated_at
    player.stats_synced_at = synced_at


async def get_player(session: AsyncSession, player_id: int):
    player = await session.get(Player, player_id)
    if player is None:
        return None
    result = await session.execute(
        select(Team, TeamParticipantMembership)
        .join(TeamParticipantMembership, Team.id == TeamParticipantMembership.team_id)
        .where(TeamParticipantMembership.player_id == player.id)
        .order_by(TeamParticipantMembership.is_active.desc(), Team.name.asc())
    )
    membership_rows = result.all()
    statuses = [
        PlayerTeamStatus(team, membership.is_active, membership.participant_type)
        for team, membership in membership_rows
    ]
    recent_rows = (await session.execute(
        select(DemoPlayerStat.internal_rating, DemoPlayerStat.rounds_played)
        .join(DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id)
        .join(DemoFile, DemoFile.id == DemoPlayerStat.demo_file_id)
        .where(DemoPlayerStat.player_id == player.id, DemoParseRun.status == "success")
        .order_by(DemoFile.match_date.desc(), DemoFile.id.desc()).limit(10)
    )).all()
    recent_rounds = sum(row.rounds_played for row in recent_rows)
    recent_rating = (
        sum((row.internal_rating * row.rounds_played for row in recent_rows), Decimal(0))
        / recent_rounds if recent_rounds else None
    )
    active_membership = next((
        item for item in membership_rows if item[1].is_active and item[1].left_at is None
    ), None)
    swing = await player_round_swing(session, player.id)
    player.round_swing = swing
    strength, breakdown = calculate_player_strength(
        player.bo3_rating, internal_rating=player.internal_rating,
        internal_maps=player.internal_rating_maps_count,
        top15_rating=player.internal_rating_top15,
        top15_maps=player.internal_rating_top15_maps_count,
        top16_30_rating=player.internal_rating_top16_30,
        top16_30_maps=player.internal_rating_top16_30_maps_count,
        recent_rating=recent_rating, recent_maps=len(recent_rows),
        role=active_membership[1].role if active_membership else None,
        round_swing_score=swing.get("score") if swing.get("status") == "complete" else None,
        round_swing_rounds=swing.get("rounds", 0), round_swing_confidence=swing.get("confidence"),
    )
    player.player_strength, player.strength_breakdown = strength, breakdown
    combat_rows = (await session.execute(
        select(DemoPlayerStat.combat_data, DemoPlayerStat.opponent_rank_group,
               DemoMapResult.map_name, DemoFile.match_date, DemoFile.id)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoPlayerStat.demo_file_id)
        .join(DemoFile, DemoFile.id == DemoPlayerStat.demo_file_id)
        .join(DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id)
        .where(DemoPlayerStat.player_id == player.id, DemoParseRun.status == "success",
               DemoMapResult.combat_data_status == "complete", DemoPlayerStat.combat_data.is_not(None))
    )).all()
    def aggregate(rows) -> dict | None:
        payloads = [row.combat_data for row in rows if row.combat_data is not None]
        if not payloads: return None
        keys = {key for payload in payloads for key, value in payload.items() if isinstance(value, int)}
        result = {key: sum(int(payload.get(key, 0)) for payload in payloads) for key in keys}
        def rate(num, den): return round(result.get(num, 0) * 100 / result.get(den, 0), 4) if result.get(den, 0) else None
        result["opening_success_rate"] = rate("opening_kills", "opening_attempts")
        result["trade_success_rate"] = rate("trade_kills", "trade_opportunities")
        deaths = result.get("deaths_traded", 0) + result.get("deaths_not_traded", 0)
        result["death_trade_rate"] = round(result.get("deaths_traded", 0) * 100 / deaths, 4) if deaths else None
        result["clutch_win_rate"] = rate("clutch_wins", "clutch_opportunities")
        return result
    ordered = sorted(combat_rows, key=lambda row: (row.match_date or datetime.min.date(), row.id), reverse=True)
    player.combat = {
        "overall": aggregate(combat_rows), "recent_10": aggregate(ordered[:10]),
        "top_15": aggregate([row for row in combat_rows if row.opponent_rank_group == "top_15"]),
        "top_16_30": aggregate([row for row in combat_rows if row.opponent_rank_group == "top_16_30"]),
        "maps": {name: aggregate([row for row in combat_rows if row.map_name == name])
                 for name in sorted({row.map_name for row in combat_rows if row.map_name})},
    }
    utility_rows = (await session.execute(
        select(DemoPlayerStat.utility_data, DemoPlayerStat.opponent_rank_group,
               DemoMapResult.map_name, DemoFile.match_date, DemoFile.id)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoPlayerStat.demo_file_id)
        .join(DemoFile, DemoFile.id == DemoPlayerStat.demo_file_id)
        .join(DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id)
        .where(DemoPlayerStat.player_id == player.id, DemoParseRun.status == "success",
               DemoMapResult.utility_data_status == "complete", DemoPlayerStat.utility_data.is_not(None))
    )).all()
    def aggregate_utility(rows):
        payloads = [row.utility_data for row in rows if row.utility_data]
        if not payloads: return None
        value = utility_base(sum(int(item.get("rounds_played", 0)) for item in payloads))
        for item in payloads:
            for key in COUNT_KEYS: value[key] += int(item.get(key, 0))
            value["enemy_flash_duration"] += float(item.get("enemy_flash_duration", 0))
            value["teammate_flash_duration"] += float(item.get("teammate_flash_duration", 0))
            for side in ("ct", "t"):
                value[side]["rounds_played"] += int(item.get(side, {}).get("rounds_played", 0))
                for key in COUNT_KEYS: value[side][key] += int(item.get(side, {}).get(key, 0))
        return finalize_utility(value)
    utility_ordered = sorted(utility_rows, key=lambda row: (row.match_date or datetime.min.date(), row.id), reverse=True)
    player.utility = {
        "overall": aggregate_utility(utility_rows),
        "recent_5": aggregate_utility(utility_ordered[:5]), "recent_10": aggregate_utility(utility_ordered[:10]),
        "recent_20": aggregate_utility(utility_ordered[:20]),
        "top_15": aggregate_utility([row for row in utility_rows if row.opponent_rank_group == "top_15"]),
        "top_16_30": aggregate_utility([row for row in utility_rows if row.opponent_rank_group == "top_16_30"]),
        "maps": {name: aggregate_utility([row for row in utility_rows if row.map_name == name])
                 for name in sorted({row.map_name for row in utility_rows if row.map_name})},
    }
    return player, statuses


async def refresh_player(
    session: AsyncSession, player_id: int, source: Bo3Client | None = None,
):
    player = await session.get(Player, player_id)
    if player is None:
        return None
    owned_source = Bo3Client() if source is None else None
    player_source = source or owned_source
    try:
        profile = await player_source.fetch_player(player.bo3_id, player.bo3_slug)
    finally:
        if owned_source is not None:
            await owned_source.aclose()
    apply_player_profile(player, profile, datetime.now(UTC))
    await session.commit()
    return await get_player(session, player_id)
