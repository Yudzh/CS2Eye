from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cs2eye.models.team import Player, TeamParticipantMembership


@dataclass(frozen=True)
class TeamStrengthFactor:
    code: str
    label: str
    kind: str
    value: float
    explanation: str
    players: list[str]


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


def _factor(
    code: str,
    label: str,
    kind: str,
    value: float,
    explanation: str,
    players: list[str] | None = None,
) -> TeamStrengthFactor:
    return TeamStrengthFactor(
        code=code,
        label=label,
        kind=kind,
        value=round(value, 2),
        explanation=explanation,
        players=players or [],
    )


def calculate_team_strength(
    roster: list[tuple[Player, TeamParticipantMembership]],
    *,
    now: datetime | None = None,
) -> TeamStrength:
    """Calculate strength using only current active player memberships."""
    active = [
        (player, membership)
        for player, membership in roster
        if membership.participant_type == "player"
        and membership.is_active
        and membership.left_at is None
    ]
    factors: list[TeamStrengthFactor] = []
    notes: list[str] = []
    missing_roles: list[str] = []

    if not active:
        factors.append(_factor(
            "no_active_players",
            "Нет активного состава",
            "penalty",
            -100,
            "В команде нет активных игроков для расчёта.",
        ))
        return TeamStrength(
            active_players_count=0,
            base_player_score=0,
            roster_bonus=0,
            roster_penalty=100,
            total_adjustment=-100,
            score_before_limits=-100,
            team_strength_score=0,
            calculation="0.00 + 0.00 - 100.00 = -100.00 → ограничено до 0.00",
            missing_required_roles=["igl", "awper"],
            factors=factors,
            notes=["Нет активных игроков для расчёта силы состава."],
        )

    strengths = [
        float(player.player_strength if player.player_strength is not None else 50)
        for player, _ in active
    ]
    base = round(sum(strengths) / len(strengths), 2)
    names = [player.nickname for player, _ in active]
    factors.append(_factor(
        "base_player_score",
        "Средняя сила игроков",
        "base",
        base,
        f"Среднее значение силы {len(active)} активных игроков.",
        names,
    ))

    count = len(active)
    if count != 5:
        penalty = min(abs(5 - count) * 10.0, 30.0)
        factors.append(_factor(
            "invalid_roster_size",
            "Некорректный размер состава",
            "penalty",
            -penalty,
            f"В основном составе должно быть ровно 5 игроков. Сейчас: {count}.",
            names,
        ))
        notes.append(f"Основной состав содержит {count}/5 игроков.")

    roles = {membership.role for _, membership in active if membership.role}
    if "igl" not in roles:
        missing_roles.append("igl")
        factors.append(_factor(
            "missing_igl", "Нет назначенного IGL", "penalty", -10,
            "В активном составе не назначен капитан / IGL.",
        ))
        notes.append("Не указан IGL в активном составе.")

    awpers = [
        (player, membership)
        for player, membership in active
        if membership.role == "awper"
    ]
    if not awpers:
        missing_roles.append("awper")
        factors.append(_factor(
            "missing_awper", "Нет назначенного AWPer", "penalty", -10,
            "В активном составе не назначен основной AWP-снайпер.",
        ))
        notes.append("Не указан AWPer в активном составе.")
    else:
        awper, _ = max(
            awpers,
            key=lambda item: item[0].player_strength
            if item[0].player_strength is not None else 50,
        )
        score = float(awper.player_strength if awper.player_strength is not None else 50)
        if score < 40:
            value, label, kind = -15.0, "Слабый AWPer", "penalty"
        elif score < 50:
            value, label, kind = -10.0, "AWPer ниже среднего", "penalty"
        elif score < 60:
            value, label, kind = -5.0, "Недостаточно сильный AWPer", "penalty"
        elif score < 70:
            value, label, kind = 0.0, "Стабильный AWPer", "info"
        elif score < 80:
            value, label, kind = 5.0, "Сильный AWPer", "bonus"
        else:
            value, label, kind = 8.0, "Звёздный AWPer", "bonus"
        factors.append(_factor(
            "awper_strength", label, kind, value,
            f"{awper.nickname}: индивидуальная сила {score:.2f}.",
            [awper.nickname],
        ))

    current_time = now or datetime.now(UTC)
    new_cutoff = current_time.date() - timedelta(days=14)
    new_players = [
        (player, membership)
        for player, membership in active
        if membership.joined_at is not None
        and membership.joined_at.date() >= new_cutoff
    ]
    unknown_dates = [
        player.nickname
        for player, membership in active
        if membership.joined_at is None
    ]
    if new_players:
        penalty = min(len(new_players) * 5.0, 15.0)
        new_names = [player.nickname for player, _ in new_players]
        factors.append(_factor(
            "very_new_players", "Недавние изменения состава", "penalty", -penalty,
            "Игроки присоединились к команде не более 14 дней назад.",
            new_names,
        ))
        notes.append(f"Есть новые игроки за последние 14 дней: {len(new_players)}.")
    elif unknown_dates:
        factors.append(_factor(
            "unknown_roster_stability", "Недостаточно данных о стабильности",
            "info", 0,
            "Не у всех активных игроков указана дата присоединения. Бонус стабильности не применяется.",
            unknown_dates,
        ))
        notes.append("Бонус стабильности не применён: не все даты вступления известны.")
    elif count == 5:
        joined_dates = [membership.joined_at for _, membership in active]
        if all(date.date() <= current_time.date() - timedelta(days=90) for date in joined_dates):
            value, code, label, days = 10.0, "stable_roster_90_days", "Стабильный состав", 90
        elif all(date.date() <= current_time.date() - timedelta(days=30) for date in joined_dates):
            value, code, label, days = 5.0, "stable_roster_30_days", "Относительно стабильный состав", 30
        else:
            value = 0
        if value:
            factors.append(_factor(
                code, label, "bonus", value,
                f"Все пять игроков находятся в составе минимум {days} дней.",
                names,
            ))
            notes.append(f"Состав стабилен минимум {days} дней.")

    bonus = round(sum(f.value for f in factors if f.kind == "bonus"), 2)
    penalty = round(abs(sum(f.value for f in factors if f.kind == "penalty")), 2)
    adjustment = round(bonus - penalty, 2)
    before_limits = round(base + adjustment, 2)
    strength = round(max(0.0, min(100.0, before_limits)), 2)
    calculation = f"{base:.2f} + {bonus:.2f} - {penalty:.2f} = {before_limits:.2f}"
    if before_limits != strength:
        calculation += f" → ограничено до {strength:.2f}"

    return TeamStrength(
        active_players_count=count,
        base_player_score=base,
        roster_bonus=bonus,
        roster_penalty=penalty,
        total_adjustment=adjustment,
        score_before_limits=before_limits,
        team_strength_score=strength,
        calculation=calculation,
        missing_required_roles=missing_roles,
        factors=factors,
        notes=notes,
    )
