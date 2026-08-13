from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Player, Team, TeamParticipantMembership
from cs2eye.services.team_strength_service import (
    TeamStrength,
    calculate_team_strength,
    load_team_performance,
)
from cs2eye.services.top_teams_service import get_team_with_roster


ROLE_ORDER = [
    "igl",
    "awper",
    "entry_frag",
    "lurk",
    "anchor_support",
    "rifler",
]
ROLE_LABELS = {
    "igl": "IGL",
    "awper": "AWPer",
    "entry_frag": "Entry Frag",
    "lurk": "Lurk",
    "anchor_support": "Anchor / Support",
    "rifler": "Rifler",
}
ADVANTAGE_THRESHOLD = 5.0
STALE_ROSTER_AFTER = timedelta(days=7)


class SameTeamComparisonError(ValueError):
    pass


class TeamNotFoundError(LookupError):
    pass


class InactiveTeamError(LookupError):
    pass


@dataclass(frozen=True)
class ComparisonPlayer:
    id: int
    nickname: str
    image_url: str | None
    role: str | None
    bo3_rating: Decimal | None
    bo3_avg_rating: Decimal | None
    internal_rating: Decimal | None
    internal_rating_version: str | None
    internal_rating_top15: Decimal | None
    internal_rating_top16_30: Decimal | None
    player_strength: int | None
    effective_player_strength: int
    strength_is_fallback: bool


@dataclass(frozen=True)
class ComparisonSide:
    team: Team
    roster: list[ComparisonPlayer]
    coaches: list[ComparisonPlayer]
    strength: TeamStrength
    relative_strength_percent: float | None


@dataclass(frozen=True)
class RoleComparison:
    role: str
    team_a_score: float | None
    team_b_score: float | None
    team_a_players: list[ComparisonPlayer]
    team_b_players: list[ComparisonPlayer]
    advantage_team_id: int | None
    advantage_team_name: str | None
    advantage_diff: float | None
    note: str


@dataclass(frozen=True)
class RankingComparison:
    rank_advantage_team_id: int | None
    rank_advantage_team_name: str | None
    rank_difference: int | None
    points_advantage_team_id: int | None
    points_advantage_team_name: str | None
    points_difference: Decimal | None


@dataclass(frozen=True)
class TeamComparison:
    team_a: ComparisonSide
    team_b: ComparisonSide
    strength_advantage_team_id: int | None
    strength_advantage_team_name: str | None
    strength_advantage_diff: float
    ranking: RankingComparison
    role_comparisons: list[RoleComparison]
    summary_notes: list[str]


class TeamComparisonService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> None:
        self._session = session
        self._now = now or datetime.now(UTC)

    async def compare(self, team_a_id: int, team_b_id: int) -> TeamComparison:
        if team_a_id == team_b_id:
            raise SameTeamComparisonError("Выберите две разные команды.")

        team_a, roster_a = await self._load_active_team(team_a_id)
        team_b, roster_b = await self._load_active_team(team_b_id)
        strength_a = calculate_team_strength(
            roster_a, now=self._now,
            performance=await load_team_performance(self._session, team_a.id, team_a.current_roster_id),
        )
        strength_b = calculate_team_strength(
            roster_b, now=self._now,
            performance=await load_team_performance(self._session, team_b.id, team_b.current_roster_id),
        )
        relative_a, relative_b = self._relative_strength(
            strength_a.team_strength_score,
            strength_b.team_strength_score,
        )
        raw_diff = round(
            strength_a.team_strength_score - strength_b.team_strength_score,
            2,
        )
        advantage_id, advantage_name = self._advantage(
            raw_diff,
            team_a,
            team_b,
        )
        players_a = self._players(roster_a, participant_type="player")
        players_b = self._players(roster_b, participant_type="player")
        roles = self._compare_roles(team_a, team_b, players_a, players_b)
        ranking = self._compare_ranking(team_a, team_b)
        side_a = ComparisonSide(
            team_a,
            players_a,
            self._players(roster_a, participant_type="coach"),
            strength_a,
            relative_a,
        )
        side_b = ComparisonSide(
            team_b,
            players_b,
            self._players(roster_b, participant_type="coach"),
            strength_b,
            relative_b,
        )
        return TeamComparison(
            team_a=side_a,
            team_b=side_b,
            strength_advantage_team_id=advantage_id,
            strength_advantage_team_name=advantage_name,
            strength_advantage_diff=abs(raw_diff),
            ranking=ranking,
            role_comparisons=roles,
            summary_notes=self._summary(
                side_a,
                side_b,
                advantage_id,
                ranking,
                roles,
            ),
        )

    async def _load_active_team(
        self,
        team_id: int,
    ) -> tuple[Team, list[tuple[Player, TeamParticipantMembership]]]:
        team, roster = await get_team_with_roster(self._session, team_id)
        if team is None:
            raise TeamNotFoundError("Команда не найдена.")
        if not team.is_analytics_active:
            raise InactiveTeamError("Команда не входит в активный Top-30.")
        return team, roster

    @staticmethod
    def _is_current(membership: TeamParticipantMembership) -> bool:
        return membership.is_active and membership.left_at is None

    @classmethod
    def _players(
        cls,
        roster: list[tuple[Player, TeamParticipantMembership]],
        *,
        participant_type: str,
    ) -> list[ComparisonPlayer]:
        return [
            ComparisonPlayer(
                id=player.id,
                nickname=player.nickname,
                image_url=player.image_url,
                role=membership.role,
                bo3_rating=player.bo3_rating,
                bo3_avg_rating=player.bo3_rating,
                internal_rating=player.internal_rating,
                internal_rating_version=player.internal_rating_version,
                internal_rating_top15=player.internal_rating_top15,
                internal_rating_top16_30=player.internal_rating_top16_30,
                player_strength=player.player_strength,
                effective_player_strength=(
                    player.player_strength
                    if player.player_strength is not None
                    else 50
                ),
                strength_is_fallback=player.player_strength is None,
            )
            for player, membership in roster
            if membership.participant_type == participant_type
            and cls._is_current(membership)
        ]

    @staticmethod
    def _relative_strength(a: float, b: float) -> tuple[float | None, float | None]:
        safe_a = max(a, 0)
        safe_b = max(b, 0)
        total = safe_a + safe_b
        if total <= 0:
            return None, None
        relative_a = round(safe_a / total * 100, 2)
        return relative_a, round(100 - relative_a, 2)

    @staticmethod
    def _advantage(
        raw_diff: float,
        team_a: Team,
        team_b: Team,
    ) -> tuple[int | None, str | None]:
        if abs(raw_diff) < ADVANTAGE_THRESHOLD:
            return None, None
        winner = team_a if raw_diff > 0 else team_b
        return winner.id, winner.name

    @classmethod
    def _compare_roles(
        cls,
        team_a: Team,
        team_b: Team,
        players_a: list[ComparisonPlayer],
        players_b: list[ComparisonPlayer],
    ) -> list[RoleComparison]:
        result = []
        for role in ROLE_ORDER:
            role_a = [player for player in players_a if player.role == role]
            role_b = [player for player in players_b if player.role == role]
            score_a = cls._role_score(role_a)
            score_b = cls._role_score(role_b)
            label = ROLE_LABELS[role]
            if score_a is None or score_b is None:
                missing = []
                if score_a is None:
                    missing.append(f"У {team_a.name} роль {label} не назначена.")
                if score_b is None:
                    missing.append(f"У {team_b.name} роль {label} не назначена.")
                advantage_id = advantage_name = advantage_diff = None
                note = " ".join(missing)
            else:
                raw_diff = round(score_a - score_b, 2)
                advantage_id, advantage_name = cls._advantage(
                    raw_diff, team_a, team_b,
                )
                advantage_diff = abs(raw_diff)
                note = (
                    f"По роли {label} явного преимущества нет."
                    if advantage_id is None
                    else f"По роли {label} преимущество у {advantage_name}: "
                    f"{score_a:g} против {score_b:g}."
                )
            result.append(RoleComparison(
                role,
                score_a,
                score_b,
                role_a,
                role_b,
                advantage_id,
                advantage_name,
                advantage_diff,
                note,
            ))
        return result

    @staticmethod
    def _role_score(players: list[ComparisonPlayer]) -> float | None:
        if not players:
            return None
        return round(
            sum(player.effective_player_strength for player in players)
            / len(players),
            2,
        )

    @staticmethod
    def _compare_ranking(team_a: Team, team_b: Team) -> RankingComparison:
        rank_winner = None
        rank_difference = None
        if team_a.current_rank is not None and team_b.current_rank is not None:
            rank_difference = abs(team_a.current_rank - team_b.current_rank)
            if team_a.current_rank != team_b.current_rank:
                rank_winner = team_a if team_a.current_rank < team_b.current_rank else team_b

        points_winner = None
        points_difference = None
        if team_a.current_points is not None and team_b.current_points is not None:
            points_difference = abs(team_a.current_points - team_b.current_points)
            if team_a.current_points != team_b.current_points:
                points_winner = team_a if team_a.current_points > team_b.current_points else team_b

        return RankingComparison(
            rank_winner.id if rank_winner else None,
            rank_winner.name if rank_winner else None,
            rank_difference,
            points_winner.id if points_winner else None,
            points_winner.name if points_winner else None,
            points_difference,
        )

    def _summary(
        self,
        side_a: ComparisonSide,
        side_b: ComparisonSide,
        advantage_id: int | None,
        ranking: RankingComparison,
        roles: list[RoleComparison],
    ) -> list[str]:
        team_a, team_b = side_a.team, side_b.team
        difference = abs(round(
            side_a.strength.team_strength_score
            - side_b.strength.team_strength_score,
            2,
        ))
        notes = [
            "По силе текущего состава явного преимущества нет."
            if advantage_id is None
            else "По силе текущего состава преимущество у "
            f"{side_a.team.name if advantage_id == team_a.id else side_b.team.name}. "
            f"Разница: {difference:.1f} пункта."
        ]
        if ranking.rank_advantage_team_id is not None:
            rank_winner = team_a if ranking.rank_advantage_team_id == team_a.id else team_b
            rank_loser = team_b if rank_winner is team_a else team_a
            notes.append(
                f"{rank_winner.name} выше в рейтинге BO3.gg: "
                f"{rank_winner.current_rank} место против {rank_loser.current_rank}."
            )
            if advantage_id is not None and advantage_id != rank_winner.id:
                strength_winner = team_a if advantage_id == team_a.id else team_b
                notes.append(
                    f"Рейтинг BO3.gg выше у {rank_winner.name}, но расчёт силы "
                    f"текущего состава показывает преимущество {strength_winner.name}."
                )
        for role in ("awper", "igl"):
            comparison = next(item for item in roles if item.role == role)
            notes.append(comparison.note)
        for side in (side_a, side_b):
            team = side.team
            if side.strength.active_players_count != 5:
                notes.append(
                    f"Состав {team.name} содержит "
                    f"{side.strength.active_players_count}/5 активных игроков."
                )
            for role in side.strength.missing_required_roles:
                notes.append(f"У {team.name} отсутствует роль {ROLE_LABELS[role]}.")
            fallback_names = [
                player.nickname for player in side.roster if player.strength_is_fallback
            ]
            if fallback_names:
                notes.append(
                    f"У игроков {team.name} отсутствует рассчитанная сила: "
                    f"{', '.join(fallback_names)}. Использовано базовое значение 50."
                )
            synced_at = team.roster_synced_at
            if synced_at is not None:
                if synced_at.tzinfo is None:
                    synced_at = synced_at.replace(tzinfo=UTC)
                if self._now - synced_at > STALE_ROSTER_AFTER:
                    notes.append(
                        f"Состав {team.name} не синхронизировался более 7 дней."
                    )
        return notes
