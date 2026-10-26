"""Explicit team identity selection; only profile fields are updated."""
from datetime import UTC, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select

from cs2eye.core.config import settings
from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.team import Team
from cs2eye.services.match_result_sync_service import MatchResultSyncService


class PandaScoreTeam(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=8)
    image_url: str | None = None

    @field_validator('image_url')
    @classmethod
    def safe_image(cls, value):
        if value and (urlparse(value).scheme != 'https' or not urlparse(value).hostname):
            raise ValueError('Invalid image URL')
        return value


class PandaScoreTeamService:
    def __init__(self, session, client_factory=PandaScoreClient):
        self.session = session
        self.client_factory = client_factory

    async def fetch(self, **params):
        if not settings.pandascore_api_token.get_secret_value():
            raise PandaScoreError('На сервере не настроен PANDASCORE_API_TOKEN.')
        # Share the transaction lock and rate budget with match synchronization.
        sync = MatchResultSyncService(self.session)
        async with sync.locked():
            quota = await sync.quota()
            client = self.client_factory(quota, lambda: sync.reserve(quota))
            try:
                rows = await client.teams(**params)
            except PandaScoreError:
                # Persist consumed requests and any provider backoff.
                await self.session.commit()
                raise
            finally:
                await client.close()
        try:
            return [PandaScoreTeam.model_validate(row) for row in rows]
        except ValidationError:
            raise PandaScoreError('PandaScore: некорректные сведения о команде.') from None

    async def search(self, query):
        return await self.fetch(**{'search[name]': query})

    async def update(self, team_id, external_id):
        rows = await self.fetch(**{'filter[id]': external_id})
        if len(rows) != 1 or rows[0].id != external_id:
            raise ValueError('Команда с таким PandaScore ID не найдена.')
        row = rows[0]
        team = await self.session.scalar(select(Team).where(Team.id == team_id).with_for_update())
        if team is None:
            raise ValueError('Команда не найдена.')
        if team.pandascore_id is not None and team.pandascore_id != external_id:
            raise ValueError('Команда уже привязана к другому PandaScore ID.')
        duplicate = await self.session.scalar(select(Team.id).where(Team.pandascore_id == external_id, Team.id != team_id))
        if duplicate is not None:
            raise ValueError('Этот PandaScore ID уже привязан к другой команде.')
        team.pandascore_id = row.id
        team.pandascore_slug = row.slug
        team.pandascore_data = row.model_dump()
        team.pandascore_synced_at = datetime.now(UTC)
        team.name = row.name
        # Missing optional values must not erase an existing useful profile.
        if row.image_url:
            team.logo_url = row.image_url
        if row.location and row.location != team.country_code:
            team.country_code = row.location
            team.country_name = None
        await self.session.flush()
        return team
