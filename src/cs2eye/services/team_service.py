from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Player, Team, TeamRosterMember

VALID_STATUSES = {
    "active",
    "coach",
}

VALID_ROLES = {
    "igl",
    "awper",
    "entry_frag",
    "lurk",
    "anchor_support",
    "coach",
}

ROLE_ALIASES = {
    "igl": "igl",
    "captain": "igl",
    "капитан": "igl",
    "in-game leader": "igl",
    "in game leader": "igl",

    "awp": "awper",
    "awper": "awper",
    "sniper": "awper",

    "entry": "entry_frag",
    "entry frag": "entry_frag",
    "entry fragger": "entry_frag",
    "entry_frag": "entry_frag",

    "lurk": "lurk",
    "lurker": "lurk",

    "anchor": "anchor_support",
    "support": "anchor_support",
    "anchor/support": "anchor_support",
    "anchor support": "anchor_support",
    "anchor_support": "anchor_support",
    "rifler": "anchor_support",
    "rifle": "anchor_support",

    "coach": "coach",
    "тренер": "coach",
}


@dataclass(frozen=True)
class RosterMemberInfo:
    roster_member_id: UUID

    player_id: UUID
    nickname: str
    real_name: str | None
    country: str | None

    status: str
    role: str | None

    joined_at: date | None
    left_at: date | None

    current_rating: float | None
    player_strength_score: float

    source_name: str | None
    source_url: str | None
    source_confidence: float

    notes: str | None


@dataclass(frozen=True)
class TeamStrengthInfo:
    team_id: UUID
    team_name: str

    active_players_count: int
    base_player_score: float

    roster_bonus: float
    roster_penalty: float

    team_strength_score: float

    missing_required_roles: list[str]
    notes: list[str]


@dataclass(frozen=True)
class TeamDetailInfo:
    id: UUID
    name: str
    country: str | None
    region: str | None
    liquipedia_url: str | None
    hltv_id: int | None

    roster: list[RosterMemberInfo]
    strength: TeamStrengthInfo


@dataclass(frozen=True)
class TeamRoleComparisonInfo:
    role: str

    team_a_score: float
    team_b_score: float

    team_a_players: list[str]
    team_b_players: list[str]

    advantage_team_name: str | None
    advantage_diff: float

    note: str


@dataclass(frozen=True)
class TeamComparisonInfo:
    team_a: TeamStrengthInfo
    team_b: TeamStrengthInfo

    strength_advantage_team_name: str | None
    strength_advantage_diff: float

    role_comparisons: list[TeamRoleComparisonInfo]

    summary_notes: list[str]


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def _required_text(value: str | None, field_name: str) -> str:
    normalized = _normalize_text(value)

    if normalized is None:
        raise ValueError(f"{field_name} is required")

    return normalized


def _normalize_status(value: str | None) -> str:
    normalized = (_normalize_text(value) or "active").casefold()

    if normalized == "benched":
        normalized = "bench"

    if normalized == "sub":
        normalized = "stand-in"

    if normalized == "substitute":
        normalized = "stand-in"

    if normalized in {"left", "removed", "kicked", "past"}:
        normalized = "former"

    if normalized not in VALID_STATUSES:
        raise ValueError(
            f"Invalid roster status: {value}. "
            f"Allowed: {', '.join(sorted(VALID_STATUSES))}"
        )

    return normalized


def _normalize_role(value: str | None) -> str | None:
    normalized = _normalize_text(value)

    if normalized is None:
        return None

    normalized = normalized.casefold()
    role = ROLE_ALIASES.get(normalized, normalized)

    if role not in VALID_ROLES:
        raise ValueError(
            f"Invalid role: {value}. "
            f"Allowed roles: {', '.join(sorted(VALID_ROLES))}"
        )

    return role


async def _get_or_create_team(
        *,
        session: AsyncSession,
        name: str,
) -> Team:
    result = await session.execute(
        select(Team)
        .where(func.lower(Team.name) == name.casefold())
    )

    team = result.scalar_one_or_none()

    if team is not None:
        return team

    team = Team(name=name)
    session.add(team)

    await session.flush()

    return team


async def _get_or_create_player(
        *,
        session: AsyncSession,
        nickname: str,
) -> Player:
    result = await session.execute(
        select(Player)
        .where(func.lower(Player.nickname) == nickname.casefold())
    )

    player = result.scalar_one_or_none()

    if player is not None:
        return player

    player = Player(
        nickname=nickname,
        player_strength_score=50.0,
    )
    session.add(player)

    await session.flush()

    return player


async def _get_current_roster_member(
        *,
        session: AsyncSession,
        team_id: UUID,
        player_id: UUID,
) -> TeamRosterMember | None:
    result = await session.execute(
        select(TeamRosterMember)
        .where(
            TeamRosterMember.team_id == team_id,
            TeamRosterMember.player_id == player_id,
            TeamRosterMember.left_at.is_(None),
        )
    )

    return result.scalar_one_or_none()


def _calculate_team_strength(
        *,
        team: Team,
        roster: list[RosterMemberInfo],
) -> TeamStrengthInfo:
    current_roster = [
        item
        for item in roster
        if item.left_at is None
    ]

    active_players = [
        item
        for item in current_roster
        if item.status in {"active", "stand-in"}
    ]

    if not active_players:
        return TeamStrengthInfo(
            team_id=team.id,
            team_name=team.name,
            active_players_count=0,
            base_player_score=0.0,
            roster_bonus=0.0,
            roster_penalty=100.0,
            team_strength_score=0.0,
            missing_required_roles=["awper", "igl"],
            notes=["Нет active-игроков для расчёта силы состава."],
        )

    base_player_score = round(
        sum(item.player_strength_score for item in active_players) / len(active_players),
        2,
    )

    roster_bonus = 0.0
    roster_penalty = 0.0
    notes: list[str] = []

    active_players_count = len(active_players)

    if active_players_count < 5:
        penalty = (5 - active_players_count) * 8
        roster_penalty += penalty
        notes.append(f"Неполный состав: active/stand-in игроков {active_players_count}/5.")

    stand_in_count = sum(
        1
        for item in active_players
        if item.status == "stand-in"
    )

    if stand_in_count > 0:
        penalty = stand_in_count * 7
        roster_penalty += penalty
        notes.append(f"Есть stand-in игроки: {stand_in_count}.")

    roles = {
        item.role
        for item in active_players
        if item.role is not None
    }

    missing_required_roles: list[str] = []

    if "awper" not in roles:
        missing_required_roles.append("awper")
        roster_penalty += 5
        notes.append("Не указан AWPer в активном составе.")

    if "igl" not in roles:
        missing_required_roles.append("igl")
        roster_penalty += 5
        notes.append("Не указан IGL в активном составе.")

    today = date.today()
    very_new_players = [
        item
        for item in active_players
        if item.joined_at is not None and item.joined_at >= today - timedelta(days=14)
    ]

    if very_new_players:
        penalty = len(very_new_players) * 3
        roster_penalty += penalty
        notes.append(f"Есть новые игроки в составе за последние 14 дней: {len(very_new_players)}.")

    stable_players = [
        item
        for item in active_players
        if item.joined_at is not None and item.joined_at <= today - timedelta(days=90)
    ]

    if active_players_count >= 5 and len(stable_players) >= 5:
        roster_bonus += 5
        notes.append("Состав стабилен минимум 90 дней.")

    team_strength_score = round(
        max(0.0, min(100.0, base_player_score + roster_bonus - roster_penalty)),
        2,
    )

    return TeamStrengthInfo(
        team_id=team.id,
        team_name=team.name,
        active_players_count=active_players_count,
        base_player_score=base_player_score,
        roster_bonus=round(roster_bonus, 2),
        roster_penalty=round(roster_penalty, 2),
        team_strength_score=team_strength_score,
        missing_required_roles=missing_required_roles,
        notes=notes,
    )

def _append_note(existing_notes: str | None, new_note: str) -> str:
    existing_notes = _normalize_text(existing_notes)

    if existing_notes is None:
        return new_note

    if new_note in existing_notes:
        return existing_notes

    return f"{existing_notes} {new_note}"


async def create_or_update_team_with_roster(
        *,
        session: AsyncSession,
        name: str,
        country: str | None,
        region: str | None,
        liquipedia_url: str | None,
        hltv_id: int | None,
        players: list[dict],
        delete_missing_current: bool = False,
) -> TeamDetailInfo:
    team_name = _required_text(name, "name")

    team = await _get_or_create_team(
        session=session,
        name=team_name,
    )

    team.country = _normalize_text(country)
    team.region = _normalize_text(region)
    team.liquipedia_url = _normalize_text(liquipedia_url)
    team.hltv_id = hltv_id

    incoming_player_ids: set[UUID] = set()

    for player_data in players:
        nickname = _required_text(
            player_data.get("nickname"),
            "players[].nickname",
        )

        player = await _get_or_create_player(
            session=session,
            nickname=nickname,
        )

        incoming_player_ids.add(player.id)

        if player_data.get("real_name") is not None:
            player.real_name = _normalize_text(player_data.get("real_name"))

        if player_data.get("country") is not None:
            player.country = _normalize_text(player_data.get("country"))

        if player_data.get("liquipedia_url") is not None:
            player.liquipedia_url = _normalize_text(player_data.get("liquipedia_url"))

        if player_data.get("hltv_id") is not None:
            player.hltv_id = player_data.get("hltv_id")

        if player_data.get("current_rating") is not None:
            player.current_rating = float(player_data["current_rating"])

        if player_data.get("player_strength_score") is not None:
            player.player_strength_score = float(player_data["player_strength_score"])

        roster_member = await _get_current_roster_member(
            session=session,
            team_id=team.id,
            player_id=player.id,
        )

        if roster_member is None:
            roster_member = TeamRosterMember(
                team_id=team.id,
                player_id=player.id,
            )
            session.add(roster_member)

        incoming_status = _normalize_status(player_data.get("status"))
        incoming_role = _normalize_role(player_data.get("role"))

        roster_member.status = incoming_status

        # Важно: Liquipedia часто не знает роли.
        # Поэтому None из Liquipedia НЕ должен стирать роль, указанную руками.
        if incoming_role is not None or roster_member.role is None:
            roster_member.role = incoming_role

        roster_member.joined_at = player_data.get("joined_at")
        roster_member.left_at = player_data.get("left_at")
        roster_member.source_name = _normalize_text(player_data.get("source_name"))
        roster_member.source_url = _normalize_text(player_data.get("source_url"))
        roster_member.source_confidence = float(player_data.get("source_confidence", 0.7))
        roster_member.notes = _normalize_text(player_data.get("notes"))

    if delete_missing_current:
        current_result = await session.execute(
            select(TeamRosterMember)
            .where(
                TeamRosterMember.team_id == team.id,
                TeamRosterMember.left_at.is_(None),
            )
        )

        for roster_member in current_result.scalars().all():
            if roster_member.player_id in incoming_player_ids:
                continue

            await session.delete(roster_member)

    await session.commit()

    return await get_team_detail(
        session=session,
        team_id=team.id,
    )


async def get_team_detail(
        *,
        session: AsyncSession,
        team_id: UUID,
) -> TeamDetailInfo:
    team_result = await session.execute(
        select(Team)
        .where(Team.id == team_id)
    )

    team = team_result.scalar_one_or_none()

    if team is None:
        raise ValueError("Team not found")

    roster_result = await session.execute(
        select(TeamRosterMember, Player)
        .join(Player, TeamRosterMember.player_id == Player.id)
        .where(
            TeamRosterMember.team_id == team.id,
            TeamRosterMember.left_at.is_(None),
        )
        .order_by(
            TeamRosterMember.status,
            Player.nickname,
        )
    )

    roster = [
        RosterMemberInfo(
            roster_member_id=roster_member.id,
            player_id=player.id,
            nickname=player.nickname,
            real_name=player.real_name,
            country=player.country,
            status=roster_member.status,
            role=roster_member.role,
            joined_at=roster_member.joined_at,
            left_at=roster_member.left_at,
            current_rating=player.current_rating,
            player_strength_score=player.player_strength_score,
            source_name=roster_member.source_name,
            source_url=roster_member.source_url,
            source_confidence=roster_member.source_confidence,
            notes=roster_member.notes,
        )
        for roster_member, player in roster_result.all()
    ]

    strength = _calculate_team_strength(
        team=team,
        roster=roster,
    )

    return TeamDetailInfo(
        id=team.id,
        name=team.name,
        country=team.country,
        region=team.region,
        liquipedia_url=team.liquipedia_url,
        hltv_id=team.hltv_id,
        roster=roster,
        strength=strength,
    )


async def list_teams(
        *,
        session: AsyncSession,
) -> list[TeamDetailInfo]:
    result = await session.execute(
        select(Team)
        .order_by(Team.name)
    )

    teams = list(result.scalars().all())

    return [
        await get_team_detail(
            session=session,
            team_id=team.id,
        )
        for team in teams
    ]


def _current_active_roster(
        team: TeamDetailInfo,
) -> list[RosterMemberInfo]:
    return [
        item
        for item in team.roster
        if item.left_at is None and item.status in {"active", "stand-in"}
    ]


def _role_key(value: str | None) -> str:
    return value or "unknown"


def _avg_score(items: list[RosterMemberInfo]) -> float:
    if not items:
        return 0.0

    return round(
        sum(item.player_strength_score for item in items) / len(items),
        2,
    )


def _player_labels(items: list[RosterMemberInfo]) -> list[str]:
    return [
        f"{item.nickname} ({item.player_strength_score})"
        for item in items
    ]


def _build_role_note(
        *,
        role: str,
        team_a_name: str,
        team_b_name: str,
        advantage_team_name: str | None,
        advantage_diff: float,
) -> str:
    if advantage_team_name is None:
        return f"Роль {role}: явного преимущества нет."

    return (
        f"Роль {role}: преимущество у {advantage_team_name}. "
        f"Разница: {advantage_diff}."
    )


def _compare_role(
        *,
        role: str,
        team_a_name: str,
        team_b_name: str,
        team_a_items: list[RosterMemberInfo],
        team_b_items: list[RosterMemberInfo],
) -> TeamRoleComparisonInfo:
    team_a_score = _avg_score(team_a_items)
    team_b_score = _avg_score(team_b_items)

    raw_diff = round(team_a_score - team_b_score, 2)
    advantage_diff = abs(raw_diff)

    if advantage_diff < 5:
        advantage_team_name = None
    elif raw_diff > 0:
        advantage_team_name = team_a_name
    else:
        advantage_team_name = team_b_name

    return TeamRoleComparisonInfo(
        role=role,
        team_a_score=team_a_score,
        team_b_score=team_b_score,
        team_a_players=_player_labels(team_a_items),
        team_b_players=_player_labels(team_b_items),
        advantage_team_name=advantage_team_name,
        advantage_diff=advantage_diff,
        note=_build_role_note(
            role=role,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            advantage_team_name=advantage_team_name,
            advantage_diff=advantage_diff,
        ),
    )


def _build_summary_notes(
        *,
        team_a: TeamDetailInfo,
        team_b: TeamDetailInfo,
        strength_advantage_team_name: str | None,
        strength_advantage_diff: float,
        role_comparisons: list[TeamRoleComparisonInfo],
) -> list[str]:
    notes: list[str] = []

    if strength_advantage_team_name is None:
        notes.append("По общей силе состава явного преимущества нет.")
    else:
        notes.append(
            f"По общей силе состава преимущество у {strength_advantage_team_name}. "
            f"Разница: {strength_advantage_diff}."
        )

    important_roles = {"awper", "igl"}

    for comparison in role_comparisons:
        if comparison.role not in important_roles:
            continue

        if comparison.advantage_team_name is not None:
            notes.append(comparison.note)

    if team_a.strength.missing_required_roles:
        notes.append(
            f"{team_a.name}: не указаны важные роли: "
            f"{', '.join(team_a.strength.missing_required_roles)}."
        )

    if team_b.strength.missing_required_roles:
        notes.append(
            f"{team_b.name}: не указаны важные роли: "
            f"{', '.join(team_b.strength.missing_required_roles)}."
        )

    if not notes:
        notes.append("Составы выглядят сопоставимо. Нужны карты, форма и турнирный контекст.")

    return notes


async def compare_teams(
        *,
        session: AsyncSession,
        team_a_id: UUID,
        team_b_id: UUID,
) -> TeamComparisonInfo:
    team_a = await get_team_detail(
        session=session,
        team_id=team_a_id,
    )
    team_b = await get_team_detail(
        session=session,
        team_id=team_b_id,
    )

    strength_raw_diff = round(
        team_a.strength.team_strength_score - team_b.strength.team_strength_score,
        2,
    )
    strength_advantage_diff = abs(strength_raw_diff)

    if strength_advantage_diff < 5:
        strength_advantage_team_name = None
    elif strength_raw_diff > 0:
        strength_advantage_team_name = team_a.name
    else:
        strength_advantage_team_name = team_b.name

    team_a_active = _current_active_roster(team_a)
    team_b_active = _current_active_roster(team_b)

    team_a_by_role: dict[str, list[RosterMemberInfo]] = {}
    team_b_by_role: dict[str, list[RosterMemberInfo]] = {}

    for item in team_a_active:
        team_a_by_role.setdefault(_role_key(item.role), []).append(item)

    for item in team_b_active:
        team_b_by_role.setdefault(_role_key(item.role), []).append(item)

    roles = sorted(
        {
            *team_a_by_role.keys(),
            *team_b_by_role.keys(),
        }
    )

    role_comparisons = [
        _compare_role(
            role=role,
            team_a_name=team_a.name,
            team_b_name=team_b.name,
            team_a_items=team_a_by_role.get(role, []),
            team_b_items=team_b_by_role.get(role, []),
        )
        for role in roles
    ]

    return TeamComparisonInfo(
        team_a=team_a.strength,
        team_b=team_b.strength,
        strength_advantage_team_name=strength_advantage_team_name,
        strength_advantage_diff=strength_advantage_diff,
        role_comparisons=role_comparisons,
        summary_notes=_build_summary_notes(
            team_a=team_a,
            team_b=team_b,
            strength_advantage_team_name=strength_advantage_team_name,
            strength_advantage_diff=strength_advantage_diff,
            role_comparisons=role_comparisons,
        ),
    )


async def get_team_detail_by_name(
        *,
        session: AsyncSession,
        team_name: str,
) -> TeamDetailInfo:
    normalized_team_name = _required_text(team_name, "team_name")

    result = await session.execute(
        select(Team)
        .where(func.lower(Team.name) == normalized_team_name.casefold())
    )

    team = result.scalar_one_or_none()

    if team is None:
        raise ValueError(f"Team not found: {normalized_team_name}")

    return await get_team_detail(
        session=session,
        team_id=team.id,
    )


async def compare_teams_by_names(
        *,
        session: AsyncSession,
        team_a_name: str,
        team_b_name: str,
) -> TeamComparisonInfo:
    team_a = await get_team_detail_by_name(
        session=session,
        team_name=team_a_name,
    )
    team_b = await get_team_detail_by_name(
        session=session,
        team_name=team_b_name,
    )

    strength_raw_diff = round(
        team_a.strength.team_strength_score - team_b.strength.team_strength_score,
        2,
    )
    strength_advantage_diff = abs(strength_raw_diff)

    if strength_advantage_diff < 5:
        strength_advantage_team_name = None
    elif strength_raw_diff > 0:
        strength_advantage_team_name = team_a.name
    else:
        strength_advantage_team_name = team_b.name

    team_a_active = _current_active_roster(team_a)
    team_b_active = _current_active_roster(team_b)

    team_a_by_role: dict[str, list[RosterMemberInfo]] = {}
    team_b_by_role: dict[str, list[RosterMemberInfo]] = {}

    for item in team_a_active:
        team_a_by_role.setdefault(_role_key(item.role), []).append(item)

    for item in team_b_active:
        team_b_by_role.setdefault(_role_key(item.role), []).append(item)

    roles = sorted(
        {
            *team_a_by_role.keys(),
            *team_b_by_role.keys(),
        }
    )

    role_comparisons = [
        _compare_role(
            role=role,
            team_a_name=team_a.name,
            team_b_name=team_b.name,
            team_a_items=team_a_by_role.get(role, []),
            team_b_items=team_b_by_role.get(role, []),
        )
        for role in roles
    ]

    return TeamComparisonInfo(
        team_a=team_a.strength,
        team_b=team_b.strength,
        strength_advantage_team_name=strength_advantage_team_name,
        strength_advantage_diff=strength_advantage_diff,
        role_comparisons=role_comparisons,
        summary_notes=_build_summary_notes(
            team_a=team_a,
            team_b=team_b,
            strength_advantage_team_name=strength_advantage_team_name,
            strength_advantage_diff=strength_advantage_diff,
            role_comparisons=role_comparisons,
        ),
    )



async def update_team_roster_manually(
        *,
        session: AsyncSession,
        team_name: str,
        players: list[dict],
) -> TeamDetailInfo:
    normalized_team_name = _required_text(team_name, "team_name")

    team_result = await session.execute(
        select(Team)
        .where(func.lower(Team.name) == normalized_team_name.casefold())
    )

    team = team_result.scalar_one_or_none()

    if team is None:
        raise ValueError(f"Team not found: {normalized_team_name}")

    for player_data in players:
        nickname = _required_text(
            player_data.get("nickname"),
            "players[].nickname",
        )

        should_delete = int(player_data.get("delete", 0)) == 1

        player_result = await session.execute(
            select(Player)
            .where(func.lower(Player.nickname) == nickname.casefold())
        )

        existing_player = player_result.scalar_one_or_none()

        if should_delete:
            if existing_player is None:
                continue

            await session.execute(
                delete(TeamRosterMember)
                .where(
                    TeamRosterMember.team_id == team.id,
                    TeamRosterMember.player_id == existing_player.id,
                )
            )

            continue

        role = _normalize_role(player_data.get("role"))

        if role is None:
            raise ValueError(
                f"Role is required for player '{nickname}' when delete=0. "
                f"Allowed roles: {', '.join(sorted(VALID_ROLES))}"
            )

        player = await _get_or_create_player(
            session=session,
            nickname=nickname,
        )

        if player_data.get("real_name") is not None:
            player.real_name = _normalize_text(player_data.get("real_name"))

        if player_data.get("country") is not None:
            player.country = _normalize_text(player_data.get("country"))

        if player_data.get("liquipedia_url") is not None:
            player.liquipedia_url = _normalize_text(player_data.get("liquipedia_url"))

        if player_data.get("hltv_id") is not None:
            player.hltv_id = player_data.get("hltv_id")

        if player_data.get("current_rating") is not None:
            player.current_rating = float(player_data["current_rating"])

        if player_data.get("player_strength_score") is not None:
            player.player_strength_score = float(player_data["player_strength_score"])

        roster_member = await _get_current_roster_member(
            session=session,
            team_id=team.id,
            player_id=player.id,
        )

        if roster_member is None:
            roster_member = TeamRosterMember(
                team_id=team.id,
                player_id=player.id,
            )
            session.add(roster_member)

        roster_member.status = "coach" if role == "coach" else "active"
        roster_member.role = role
        roster_member.joined_at = player_data.get("joined_at")
        roster_member.left_at = player_data.get("left_at")
        roster_member.source_name = "manual"
        roster_member.source_url = _normalize_text(player_data.get("source_url"))
        roster_member.source_confidence = 1.0
        roster_member.notes = _normalize_text(player_data.get("notes"))

    await session.commit()

    return await get_team_detail(
        session=session,
        team_id=team.id,
    )


async def delete_team_by_name(
        *,
        session: AsyncSession,
        team_name: str,
) -> str:
    normalized_team_name = _required_text(team_name, "team_name")

    result = await session.execute(
        select(Team)
        .where(func.lower(Team.name) == normalized_team_name.casefold())
    )

    team = result.scalar_one_or_none()

    if team is None:
        raise ValueError(f"Team not found: {normalized_team_name}")

    deleted_team_name = team.name

    await session.delete(team)
    await session.commit()

    return deleted_team_name