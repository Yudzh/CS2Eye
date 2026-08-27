from datetime import UTC, datetime
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.integrations.bo3.client import Bo3Client
from cs2eye.models.team import Player, Team, TeamParticipantMembership
from cs2eye.services.team_roster_service import set_current_roster

class TeamImportService:
    def __init__(self, session: AsyncSession): self.session = session

    async def import_bo3(self, slug_or_url: str) -> Team:
        slug = slug_or_url.strip().rstrip("/").split("/")[-1]
        if not re.fullmatch(r"[a-z0-9-]+", slug): raise ValueError("Укажите корректный BO3 slug или URL команды.")
        async with Bo3Client() as client: detail = await client.fetch_team(None, slug)
        raw = detail.raw_payload
        team = (await self.session.execute(select(Team).where(Team.bo3_id == detail.id))).scalar_one_or_none()
        if team is None:
            team = Team(bo3_id=detail.id, bo3_slug=detail.slug, name=raw.get("name") or detail.slug, is_analytics_active=False)
            self.session.add(team)
        team.bo3_slug = detail.slug; team.name = raw.get("name") or team.name
        team.logo_url = raw.get("image_url") or raw.get("logo_url")
        country = raw.get("country") or {}; team.country_code = country.get("code"); team.country_name = country.get("name")
        team.region = raw.get("region") or team.region; team.roster_synced_at = datetime.now(UTC)
        await self.session.flush()
        current_players = []
        for item in detail.players:
            player = (await self.session.execute(select(Player).where(Player.bo3_id == item.id))).scalar_one_or_none()
            if player is None:
                player = Player(bo3_id=item.id, bo3_slug=item.slug, nickname=item.nickname, is_analytics_active=False); self.session.add(player)
            player.bo3_slug=item.slug; player.nickname=item.nickname; player.image_url=item.image_url
            if item.country: player.country_code=item.country.code; player.country_name=item.country.name
            await self.session.flush()
            membership = (await self.session.execute(select(TeamParticipantMembership).where(TeamParticipantMembership.team_id==team.id, TeamParticipantMembership.player_id==player.id, TeamParticipantMembership.is_active.is_(True)))).scalar_one_or_none()
            role = "coach" if item.is_coach else "substitute" if item.is_substitute else "player"
            if membership is None: self.session.add(TeamParticipantMembership(team_id=team.id, player_id=player.id, participant_type=role))
            else: membership.participant_type=role
            if role == "player": current_players.append(player)
        if len({p.id for p in current_players}) == 5: await set_current_roster(self.session, team.id, current_players, source="team_import", active_from=None, active_from_source="unknown")
        await self.session.flush(); return team
