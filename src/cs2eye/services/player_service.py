from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.integrations.bo3.client import Bo3Client
from cs2eye.integrations.bo3.client import Bo3PlayerResponse
from cs2eye.models.team import Player, Team, TeamParticipantMembership


@dataclass(frozen=True)
class PlayerTeamStatus:
    team: Team
    is_active: bool
    participant_type: str


def calculate_player_strength(rating: Decimal | None) -> tuple[int | None, dict | None]:
    """Map BO3's 0–10 rating to a transparent 0–100 score."""
    if rating is None:
        return None, None
    bounded = max(Decimal("0"), min(Decimal("10"), rating))
    strength = int((bounded * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    delta = strength - 50
    direction = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
    explanation = {
        "positive": "Рейтинг BO3.gg выше нейтрального уровня 5.0.",
        "negative": "Рейтинг BO3.gg ниже нейтрального уровня 5.0.",
        "neutral": "Рейтинг BO3.gg соответствует нейтральному уровню 5.0.",
    }[direction]
    return strength, {
        "baseline": 50,
        "formula": "player_strength = clamp(bo3_rating, 0, 10) × 10",
        "factors": [{
            "metric": "bo3_rating_6_months", "value": float(rating),
            "impact": delta, "direction": direction, "explanation": explanation,
        }],
    }


def apply_player_profile(player: Player, profile: Bo3PlayerResponse, synced_at: datetime) -> None:
    strength, breakdown = calculate_player_strength(profile.six_month_avg_rating)
    player.bo3_slug = profile.slug
    player.nickname = profile.nickname
    player.first_name = profile.first_name
    player.last_name = profile.last_name
    player.image_url = profile.image_url
    player.country_code = profile.country.code if profile.country else None
    player.country_name = profile.country.name if profile.country else None
    player.bo3_rating = profile.six_month_avg_rating
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
    statuses = [
        PlayerTeamStatus(team, membership.is_active, membership.participant_type)
        for team, membership in result.all()
    ]
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
