from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.scoring.config import TEAM_WEIGHTS, normalize
from cs2eye.analytics.scoring.core import FactorInput, ScoringFactor, score_factors
from cs2eye.models.team import Player, TeamParticipantMembership
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.analytics.scoring.core import regress_rate


@dataclass(frozen=True)
class TeamPerformanceInput:
    overall_score: float | None = None
    overall_sample: int = 0
    top15_score: float | None = None
    top15_sample: int = 0
    top16_30_score: float | None = None
    top16_30_sample: int = 0
    recent10_score: float | None = None
    recent10_sample: int = 0
    recent5_score: float | None = None
    recent5_sample: int = 0
    roster_maps: int = 0


async def load_team_performance(
    session: AsyncSession, team_id: int, roster_id: int | None = None,
) -> TeamPerformanceInput:
    """Объединить агрегаты карт, не включая bomb analytics в силу команды."""
    query = select(TeamMapAggregate).where(
        TeamMapAggregate.team_id == team_id,
        TeamMapAggregate.aggregation_level == "organization",
        TeamMapAggregate.scope_key.in_(("all", "recent:5", "recent:10", "rank:top_15", "rank:top_16_30")),
    )
    rows = list((await session.execute(query)).scalars())

    def combined(scope_key: str) -> tuple[float | None, int]:
        selected = [row for row in rows if row.scope_key == scope_key]
        maps = sum(row.maps_played for row in selected)
        rounds = sum(row.rounds_played for row in selected)
        if not maps and not rounds:
            return None, 0
        map_rate, _ = regress_rate(sum(row.maps_won for row in selected), maps, prior_size=8)
        round_rate, _ = regress_rate(sum(row.rounds_won for row in selected), rounds, prior_size=24)
        return round((map_rate * .60 + round_rate * .40) * 100, 2), maps

    overall, overall_n = combined("all")
    top15, top15_n = combined("rank:top_15")
    top30, top30_n = combined("rank:top_16_30")
    recent10, recent10_n = combined("recent:10")
    recent5, recent5_n = combined("recent:5")
    roster_maps = 0
    if roster_id is not None:
        roster_rows = (await session.execute(select(TeamMapAggregate.maps_played).where(
            TeamMapAggregate.team_id == team_id,
            TeamMapAggregate.aggregation_level == "roster",
            TeamMapAggregate.roster_id == roster_id,
            TeamMapAggregate.scope_key == "all",
        ))).scalars().all()
        roster_maps = sum(roster_rows)
    return TeamPerformanceInput(overall, overall_n, top15, top15_n, top30, top30_n,
                                recent10, recent10_n, recent5, recent5_n, roster_maps)


@dataclass(frozen=True)
class TeamStrengthFactor:
    key: str
    label: str
    raw_value: object
    normalized_score: float | None
    weight: float
    effective_weight: float
    impact: float
    sample_size: int | None
    confidence: float | None
    reason: str | None
    available: bool
    reference_value: float | None = None
    reference_source: str | None = None

    # Прежние имена сохранены для совместимости потребителей при переходе на V2.
    @property
    def code(self) -> str: return self.key
    @property
    def kind(self) -> str: return "bonus" if self.impact > 0 else "penalty" if self.impact < 0 else "info"
    @property
    def value(self) -> float: return self.impact
    @property
    def explanation(self) -> str: return self.reason or ""
    @property
    def players(self) -> list[str]: return []


@dataclass(frozen=True)
class TeamStrength:
    active_players_count: int
    base_player_score: float
    roster_bonus: float
    roster_penalty: float
    total_adjustment: float
    score_before_limits: float
    team_strength_score: float
    calculation: str
    missing_required_roles: list[str]
    factors: list[TeamStrengthFactor]
    notes: list[str]
    model_version: str = "v2"
    raw_score: float = 50.0
    reliability: float = 0.0
    confidence_adjustment: float = 0.0
    final_score: float = 50.0
    team_strength_raw_score: float = 50.0
    team_strength_reliability: float = 0.0
    team_strength_model_version: str = "v2"


def _roster_quality(strengths: list[float]) -> tuple[float, dict[str, float]]:
    ordered = sorted(strengths, reverse=True)
    average = sum(ordered) / len(ordered)
    top = sum(ordered[:min(2, len(ordered))]) / min(2, len(ordered))
    bottom = sum(ordered[-min(2, len(ordered)):]) / min(2, len(ordered))
    return average * .70 + top * .15 + bottom * .15, {
        "average": round(average, 2), "top_2_average": round(top, 2),
        "bottom_2_average": round(bottom, 2),
    }


def _stability(
    active: list[tuple[Player, TeamParticipantMembership]], now: datetime,
    roster_maps: int,
) -> tuple[float | None, float, str]:
    dates = [membership.joined_at for _, membership in active]
    if len(active) != 5 or any(value is None for value in dates):
        return None, .2, "Нет дат состава или полной активной пятёрки; пробелы в метаданных не уменьшают силу."
    oldest_change_days = min(max(0, (now.date() - value.date()).days) for value in dates if value)
    days_score = normalize(float(oldest_change_days), "roster_days")
    maps_score = normalize(float(roster_maps), "roster_maps") if roster_maps else 50.0
    score = days_score * .70 + maps_score * .30
    return score, min(1.0, .5 + roster_maps / 40), (
        f"Непрерывная стабильность: последний участник присоединился {oldest_change_days} дней назад "
        f"(70%); выборка текущей пятёрки — {roster_maps} карт (30%)."
    )


def calculate_team_strength(
    roster: list[tuple[Player, TeamParticipantMembership]], *,
    now: datetime | None = None, performance: TeamPerformanceInput | None = None,
) -> TeamStrength:
    active = [(p, m) for p, m in roster if m.participant_type == "player" and m.is_active and m.left_at is None]
    performance = performance or TeamPerformanceInput()
    strengths = [float(p.player_strength) for p, _ in active if p.player_strength is not None]
    roster_score, roster_raw = _roster_quality(strengths) if strengths else (0.0, {})
    roster_available = bool(strengths)
    roster_confidence = len(strengths) / 5

    strong_parts = []
    if performance.top15_score is not None:
        strong_parts.append((performance.top15_score, .65, performance.top15_sample))
    if performance.top16_30_score is not None:
        strong_parts.append((performance.top16_30_score, .35, performance.top16_30_sample))
    strong_weight = sum(item[1] for item in strong_parts)
    strong_score = sum(item[0] * item[1] for item in strong_parts) / strong_weight if strong_weight else None
    strong_sample = sum(item[2] for item in strong_parts)

    recent_parts = []
    if performance.recent10_score is not None:
        recent_parts.append((performance.recent10_score, .60, performance.recent10_sample))
    if performance.recent5_score is not None:
        recent_parts.append((performance.recent5_score, .40, performance.recent5_sample))
    recent_weight = sum(item[1] for item in recent_parts)
    recent_score = sum(item[0] * item[1] for item in recent_parts) / recent_weight if recent_weight else None
    recent_sample = max((item[2] for item in recent_parts), default=0)  # окна пересекаются

    stability, stability_confidence, stability_reason = _stability(
        active, now or datetime.now(UTC), performance.roster_maps,
    )
    factors = [
        FactorInput("roster_quality", "Качество состава", roster_raw or None,
                    roster_score if roster_available else None, TEAM_WEIGHTS["roster_quality"],
                    len(strengths), roster_confidence,
                    "70% среднего активных игроков, 15% среднего двух лучших и 15% среднего двух слабейших.", roster_available),
        FactorInput("team_performance", "Результаты команды", performance.overall_score,
                    performance.overall_score, TEAM_WEIGHTS["team_performance"],
                    performance.overall_sample, min(1, performance.overall_sample / 10),
                    "Общие результаты по картам и раундам из разобранных демо.", performance.overall_score is not None),
        FactorInput("strong_opponents", "Игра против сильных соперников", {"top15_weight": .65, "top16_30_weight": .35},
                    strong_score, TEAM_WEIGHTS["strong_opponents"], strong_sample,
                    min(1, strong_sample / 10), "Top 1–15 имеет внутренний вес 65%, Top 16–30 — 35%.", strong_score is not None),
        FactorInput("recent_form", "Текущая форма", {"last10_weight": .60, "last5_weight": .40},
                    recent_score, TEAM_WEIGHTS["recent_form"], recent_sample,
                    min(1, recent_sample / 10), "60% последних 10 и 40% последних 5 карт; окна пересекаются, поэтому надёжность использует большую выборку.", recent_score is not None),
        FactorInput("roster_stability", "Стабильность состава", None, stability,
                    TEAM_WEIGHTS["roster_stability"], performance.roster_maps,
                    stability_confidence, stability_reason, stability is not None),
    ]
    available_conf = [f.confidence for f in factors if f.available and f.confidence is not None]
    reliability = sum(available_conf) / len(available_conf) if available_conf else 0.0
    result = score_factors(factors, reliability)
    converted = [TeamStrengthFactor(**factor.__dict__) for factor in result.factors]
    missing_roles = [role for role in ("igl", "awper") if role not in {m.role for _, m in active}]
    notes = []
    if missing_roles:
        notes.append("Данные о ролях неполны: это снижает только надёжность данных и не штрафует силу.")
    base = round(sum(strengths) / len(strengths), 2) if strengths else 50.0
    positives = round(sum(max(0, factor.impact) for factor in converted), 2)
    negatives = round(abs(sum(min(0, factor.impact) for factor in converted)), 2)
    return TeamStrength(
        len(active), base, positives, negatives, round(positives - negatives, 2),
        result.raw_score, result.final_score,
        f"50.00 + вклады {result.raw_score - 50:+.2f} = {result.raw_score:.2f}; надёжность {result.reliability:.4f} → {result.final_score:.2f}",
        missing_roles, converted, notes, result.model_version, result.raw_score,
        result.reliability, result.confidence_adjustment, result.final_score,
        result.raw_score, result.reliability, result.model_version,
    )
