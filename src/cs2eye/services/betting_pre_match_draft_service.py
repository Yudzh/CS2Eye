from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.services.demo_team_map_stats_service import (
    TeamMapMatchupItem,
    TeamMapMatchupResult,
    get_team_map_matchup,
)
from cs2eye.services.team_service import (
    TeamComparisonInfo,
    compare_teams_by_names,
)


@dataclass(frozen=True)
class BettingDraftSignal:
    edge_team_name: str | None
    edge_score: float

    bet_signal: str
    risk_level: str
    confidence_level: str

    explanation: str


@dataclass(frozen=True)
class BettingPreMatchDraft:
    team_a_name: str
    team_b_name: str
    map_name: str | None

    roster_comparison: TeamComparisonInfo
    map_matchup: TeamMapMatchupResult

    draft_signal: BettingDraftSignal
    notes: list[str]


def _same_team(
        left: str | None,
        right: str | None,
) -> bool:
    if left is None or right is None:
        return False

    return left.strip().casefold() == right.strip().casefold()


def _map_confidence_weight(confidence_level: str) -> float:
    if confidence_level == "high":
        return 1.0

    if confidence_level == "medium":
        return 0.7

    if confidence_level == "low":
        return 0.35

    return 0.1


def _add_edge(
        *,
        team_name: str | None,
        edge: float,
        team_a_name: str,
        team_b_name: str,
        team_a_score: float,
        team_b_score: float,
) -> tuple[float, float]:
    if team_name is None:
        return team_a_score, team_b_score

    if _same_team(team_name, team_a_name):
        return team_a_score + edge, team_b_score

    if _same_team(team_name, team_b_name):
        return team_a_score, team_b_score + edge

    return team_a_score, team_b_score


def _calculate_edge_scores(
        *,
        team_a_name: str,
        team_b_name: str,
        roster_comparison: TeamComparisonInfo,
        map_items: list[TeamMapMatchupItem],
) -> tuple[float, float]:
    team_a_score = 0.0
    team_b_score = 0.0

    if roster_comparison.strength_advantage_team_name is not None:
        roster_edge = roster_comparison.strength_advantage_diff * 0.8

        team_a_score, team_b_score = _add_edge(
            team_name=roster_comparison.strength_advantage_team_name,
            edge=roster_edge,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            team_a_score=team_a_score,
            team_b_score=team_b_score,
        )

    for item in map_items:
        if item.advantage_team_name is None:
            continue

        if item.matchup_confidence_level == "not_enough_data":
            continue

        map_edge = item.advantage_score * _map_confidence_weight(
            item.matchup_confidence_level
        )

        team_a_score, team_b_score = _add_edge(
            team_name=item.advantage_team_name,
            edge=map_edge,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            team_a_score=team_a_score,
            team_b_score=team_b_score,
        )

    return round(team_a_score, 2), round(team_b_score, 2)


def _has_roster_risk(
        *,
        roster_comparison: TeamComparisonInfo,
) -> bool:
    return (
        roster_comparison.team_a.active_players_count < 5
        or roster_comparison.team_b.active_players_count < 5
        or bool(roster_comparison.team_a.missing_required_roles)
        or bool(roster_comparison.team_b.missing_required_roles)
    )


def _get_risk_level(
        *,
        roster_comparison: TeamComparisonInfo,
        map_items: list[TeamMapMatchupItem],
) -> str:
    if _has_roster_risk(roster_comparison=roster_comparison):
        return "high"

    if not map_items:
        return "high"

    low_confidence_maps = [
        item
        for item in map_items
        if item.matchup_confidence_level in {"low", "not_enough_data"}
    ]

    if len(low_confidence_maps) >= max(1, len(map_items) // 2):
        return "high"

    if any(item.matchup_confidence_level == "low" for item in map_items):
        return "medium"

    return "medium"


def _get_bet_signal(
        *,
        edge_score: float,
        map_items: list[TeamMapMatchupItem],
) -> str:
    if not map_items:
        return "not_enough_data"

    if edge_score < 8:
        return "no_clear_edge"

    if edge_score < 18:
        return "statistical_edge"

    return "strong_statistical_edge"


def _get_confidence_level(
        *,
        edge_score: float,
        risk_level: str,
        map_items: list[TeamMapMatchupItem],
) -> str:
    if not map_items:
        return "low"

    if risk_level == "high":
        return "low"

    if edge_score >= 18:
        return "medium"

    if edge_score >= 8:
        return "medium"

    return "low"


def _build_signal(
        *,
        team_a_name: str,
        team_b_name: str,
        roster_comparison: TeamComparisonInfo,
        map_items: list[TeamMapMatchupItem],
) -> BettingDraftSignal:
    team_a_score, team_b_score = _calculate_edge_scores(
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        roster_comparison=roster_comparison,
        map_items=map_items,
    )

    edge_score = round(abs(team_a_score - team_b_score), 2)

    if edge_score < 8:
        edge_team_name = None
    elif team_a_score > team_b_score:
        edge_team_name = team_a_name
    else:
        edge_team_name = team_b_name

    risk_level = _get_risk_level(
        roster_comparison=roster_comparison,
        map_items=map_items,
    )

    bet_signal = _get_bet_signal(
        edge_score=edge_score,
        map_items=map_items,
    )

    confidence_level = _get_confidence_level(
        edge_score=edge_score,
        risk_level=risk_level,
        map_items=map_items,
    )

    if bet_signal == "not_enough_data":
        explanation = (
            "Недостаточно данных по картам. Пока нельзя делать даже черновой вывод."
        )
    elif bet_signal == "no_clear_edge":
        explanation = (
            "Явного преимущества нет. По текущим данным лучше не делать вывод только на основе состава и карт."
        )
    else:
        explanation = (
            f"По текущим данным есть статистическое преимущество у {edge_team_name}. "
            "Это ещё не value-ставка, потому что коэффициенты букмекера пока не учитываются."
        )

    return BettingDraftSignal(
        edge_team_name=edge_team_name,
        edge_score=edge_score,
        bet_signal=bet_signal,
        risk_level=risk_level,
        confidence_level=confidence_level,
        explanation=explanation,
    )


def _build_notes(
        *,
        roster_comparison: TeamComparisonInfo,
        map_items: list[TeamMapMatchupItem],
        draft_signal: BettingDraftSignal,
) -> list[str]:
    notes: list[str] = []

    notes.extend(roster_comparison.summary_notes)

    strong_map_edges = [
        item
        for item in map_items
        if item.recommendation in {"map_advantage", "strong_map_advantage"}
    ]

    if strong_map_edges:
        for item in strong_map_edges[:3]:
            notes.append(
                f"Карта {item.map_name}: преимущество у {item.advantage_team_name}, "
                f"разница силы карты {item.advantage_score}, "
                f"доверие {item.matchup_confidence_level}."
            )
    else:
        notes.append("По картам пока нет сильного подтверждённого преимущества.")

    low_data_maps = [
        item
        for item in map_items
        if item.matchup_confidence_level in {"low", "not_enough_data"}
    ]

    if low_data_maps:
        notes.append(
            f"Есть карты с низким доверием или без данных: {len(low_data_maps)}."
        )

    if draft_signal.bet_signal in {"statistical_edge", "strong_statistical_edge"}:
        notes.append(
            "Следующий обязательный шаг — добавить коэффициенты, чтобы отличать обычное преимущество от value."
        )

    if not notes:
        notes.append("Данных мало. Нужны карты, составы, форма и коэффициенты.")

    return notes


async def build_pre_match_draft(
        *,
        session: AsyncSession,
        team_a_name: str,
        team_b_name: str,
        map_name: str | None = None,
) -> BettingPreMatchDraft:
    if team_a_name.strip().casefold() == team_b_name.strip().casefold():
        raise ValueError("team_a_name and team_b_name must be different")

    roster_comparison = await compare_teams_by_names(
        session=session,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
    )

    map_matchup = await get_team_map_matchup(
        session=session,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        map_name=map_name,
    )

    draft_signal = _build_signal(
        team_a_name=roster_comparison.team_a.team_name,
        team_b_name=roster_comparison.team_b.team_name,
        roster_comparison=roster_comparison,
        map_items=map_matchup.items,
    )

    notes = _build_notes(
        roster_comparison=roster_comparison,
        map_items=map_matchup.items,
        draft_signal=draft_signal,
    )

    return BettingPreMatchDraft(
        team_a_name=roster_comparison.team_a.team_name,
        team_b_name=roster_comparison.team_b.team_name,
        map_name=map_name,
        roster_comparison=roster_comparison,
        map_matchup=map_matchup,
        draft_signal=draft_signal,
        notes=notes,
    )