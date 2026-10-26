from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from cs2eye.core.config import settings


class PandaScoreError(Exception):
    """Safe messages only: never retain a response, request, or token."""


class PandaScoreClient:
    def __init__(self, quota, reserve, transport=None):
        self.quota = quota
        self.reserve = reserve
        self.calls = 0
        self.client = httpx.AsyncClient(
            base_url="https://api.pandascore.co", timeout=20, transport=transport,
            headers={"Authorization": f"Bearer {settings.pandascore_api_token.get_secret_value()}"},
        )

    async def close(self):
        await self.client.aclose()

    async def past(self, **params):
        return await self.matches('past', **params)

    async def upcoming(self, **params):
        return await self.matches('upcoming', **params)

    async def matches(self, kind, **params):
        """Complete paginated list, or fail without applying a partial candidate set."""
        items = []
        for page in range(1, settings.result_sync_max_requests + 1):
            if self.calls >= settings.result_sync_max_requests:
                raise PandaScoreError("Лимит запросов за запуск; проверка будет продолжена позже.")
            await self.reserve()
            self.calls += 1
            try:
                response = await self.client.get(f'/csgo/matches/{kind}', params={
                    **params, 'per_page': 100, 'page': page, 'sort': 'begin_at'})
            except httpx.RequestError:
                raise PandaScoreError("PandaScore: ошибка сети или таймаут.") from None
            now = datetime.now(UTC)
            if response.status_code == 429 or response.headers.get('X-Rate-Limit-Remaining') == '0':
                # Conservative fallback: do not assume an undocumented reset header.
                until = now + timedelta(hours=1)
                retry = response.headers.get('Retry-After', '')
                try:
                    until = max(until, now + timedelta(seconds=int(retry)))
                except ValueError:
                    try:
                        until = max(until, parsedate_to_datetime(retry))
                    except (ValueError, TypeError):
                        pass
                self.quota.blocked_until = until
            if response.status_code in (401, 403):
                self.quota.blocked_until = now + timedelta(minutes=15)
                raise PandaScoreError("PandaScore: токен недействителен или тариф не разрешает доступ.")
            if response.status_code == 429:
                raise PandaScoreError("PandaScore: исчерпан лимит запросов; повтор отложен.")
            if response.status_code >= 500:
                raise PandaScoreError("PandaScore временно недоступен (5xx).")
            if response.status_code != 200:
                raise PandaScoreError(f"PandaScore: HTTP {response.status_code}.")
            try:
                rows = response.json()
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    raise ValueError
            except ValueError:
                raise PandaScoreError("PandaScore: некорректный ответ API.") from None
            items.extend(rows)
            if len(rows) < 100:
                return items
        raise PandaScoreError("PandaScore: слишком много страниц; требуется более узкая привязка.")
