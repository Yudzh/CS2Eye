import asyncio
import ssl
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cs2eye.core.config import settings

RANKING_TEAMS_COUNT = 40
ACTIVE_TEAMS_COUNT = 30
RANKING_PAGE_SIZE = 30
REQUEST_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (0.5, 1.5)

RANKING_ENDPOINT = "/team_rankings"
TEAM_ENDPOINT = "/api/v1/teams/{slug}"
PLAYER_ENDPOINT = "/api/v1/players/{slug}"
RANKING_PAGE_URL = (
    "https://bo3.gg/teams/valve-rankings/world"
)



class Bo3RankingError(RuntimeError):
    """BO3.gg could not provide a trustworthy top-40."""


class Bo3Country(BaseModel):
    code: str | None = None
    name: str | None = None


class Bo3TeamData(BaseModel):
    id: int
    slug: str
    name: str
    image_url: str | None = None
    country: Bo3Country | None = None


class Bo3RosterPlayer(BaseModel):
    id: int | None = None
    nickname: str
    slug: str | None = None
    score: Decimal | None = None
    image_url: str | None = None
    country_code: str | None = None


class Bo3RankingItem(BaseModel):
    id: int
    team_id: int
    region: str | None = None
    ranking_date: date
    score: Decimal
    rank: int
    rank_diff: int | None = None
    team: Bo3TeamData
    roster_players: list[Bo3RosterPlayer]


class Bo3RankingMeta(BaseModel):
    ranking_date: date
    current_page: int
    per_page: int
    total_count: int
    source: str | None = None
    is_official: bool | None = None
    updated_at: str | None = None


class Bo3PlayerTransfer(BaseModel):
    player_id: int | None = None
    team_to_id: int | None = None
    team_from_id: int | None = None
    action_date: date | None = None
    action_type: int | None = None


class Bo3RankingResponse(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    data: list[Bo3RankingItem]
    meta: Bo3RankingMeta
    raw_payload: dict[str, Any]


class Bo3TeamParticipant(BaseModel):
    id: int
    slug: str
    nickname: str
    image_url: str | None = None
    country: Bo3Country | None = None
    is_coach: bool | None = False
    status: int | None = None
    team_id: int | None = None
    is_substitute: bool = False
    player_transfers: list[Bo3PlayerTransfer] = Field(
        default_factory=list,
    )


class Bo3TeamResponse(BaseModel):
    id: int
    slug: str
    players: list[Bo3TeamParticipant]
    from_transfers: list[Bo3PlayerTransfer] = Field(
        default_factory=list,
    )
    raw_payload: dict[str, Any]


class Bo3PlayerResponse(BaseModel):
    id: int
    slug: str
    nickname: str
    first_name: str | None = None
    last_name: str | None = None
    image_url: str | None = None
    country: Bo3Country | None = None
    team: Bo3TeamData | None = None
    status: int | None = None
    six_month_avg_rating: Decimal | None = None
    updated_at: datetime | None = None
    raw_payload: dict[str, Any]


class Bo3Client:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=settings.bo3_request_timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": settings.bo3_user_agent,
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "Bo3Client":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    @property
    def source_url(self) -> str:
        return RANKING_PAGE_URL

    async def _get_with_retries(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        for attempt in range(REQUEST_ATTEMPTS):
            try:
                return await self._http_client.get(url, **kwargs)
            except (httpx.RequestError, ssl.SSLError):
                if attempt == REQUEST_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt])
        raise RuntimeError("BO3.gg request retry loop ended unexpectedly.")

    async def fetch_team(
        self,
        team_id: int,
        slug: str,
    ) -> Bo3TeamResponse:
        url = (
            f"{settings.bo3_site_base_url}"
            f"{TEAM_ENDPOINT.format(slug=slug)}"
        )
        try:
            response = await self._get_with_retries(
                url,
                headers={"Referer": f"https://bo3.gg/teams/{slug}"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise Bo3RankingError(
                f"BO3.gg team request failed for {slug}: "
                f"HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.RequestError, ssl.SSLError) as exc:
            raise Bo3RankingError(
                f"BO3.gg team request failed for {slug}: "
                f"{type(exc).__name__}: {exc} "
                f"after {REQUEST_ATTEMPTS} attempts."
            ) from exc
        except ValueError as exc:
            raise Bo3RankingError(
                f"BO3.gg returned invalid team JSON for {slug}."
            ) from exc
        if not isinstance(payload, dict):
            raise Bo3RankingError(
                f"BO3.gg returned invalid team data for {slug}."
            )
        try:
            result = Bo3TeamResponse(
                id=payload["id"],
                slug=payload["slug"],
                players=payload["players"],
                from_transfers=payload.get("from_transfers", []),
                raw_payload=payload,
            )
        except (KeyError, ValidationError) as exc:
            raise Bo3RankingError(
                "BO3.gg team response has an unexpected "
                f"format for {slug}."
            ) from exc

        if result.id != team_id or result.slug != slug:
            raise Bo3RankingError(
                f"BO3.gg returned a different team for {slug}."
            )
        participant_ids = {item.id for item in result.players}
        if len(participant_ids) != len(result.players):
            raise Bo3RankingError(
                f"BO3.gg roster validation failed for {slug}: "
                "duplicate participant."
            )
        return result

    async def fetch_player(
        self,
        player_id: int,
        slug: str,
    ) -> Bo3PlayerResponse:
        url = f"{settings.bo3_site_base_url}{PLAYER_ENDPOINT.format(slug=slug)}"
        try:
            response = await self._get_with_retries(
                url,
                headers={"Referer": f"https://bo3.gg/players/{slug}"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise Bo3RankingError(
                f"BO3.gg player request failed for {slug}: HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.RequestError, ssl.SSLError) as exc:
            raise Bo3RankingError(
                f"BO3.gg player request failed for {slug}: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise Bo3RankingError(f"BO3.gg returned invalid player JSON for {slug}.") from exc
        try:
            result = Bo3PlayerResponse(**payload, raw_payload=payload)
        except (TypeError, ValidationError) as exc:
            raise Bo3RankingError(
                f"BO3.gg player response has an unexpected format for {slug}."
            ) from exc
        if result.id != player_id or result.slug != slug:
            raise Bo3RankingError(f"BO3.gg returned a different player for {slug}.")
        return result

    async def fetch_top_teams(
            self,
    ) -> Bo3RankingResponse:
        try:
            page_payloads: list[dict[str, Any]] = []
            for page in range(
                1,
                (RANKING_TEAMS_COUNT + RANKING_PAGE_SIZE - 1)
                // RANKING_PAGE_SIZE + 1,
            ):
                response = await self._get_with_retries(
                    f"{settings.bo3_api_base_url}{RANKING_ENDPOINT}",
                    params={
                        "scope": "cs2",
                        "with": (
                            "team,"
                            "team_valve_rankings_players"
                        ),
                        "filter[discipline_id][eq]": 1,
                        "pagination[per_page]": RANKING_PAGE_SIZE,
                        "page": page,
                    },
                    headers={
                        "Origin": "https://bo3.gg",
                        "Referer": RANKING_PAGE_URL,
                    },
                )
                response.raise_for_status()
                page_payload = response.json()
                if not isinstance(page_payload, dict):
                    raise Bo3RankingError(
                        "BO3.gg returned a non-object response."
                    )
                if page_payload.get("code"):
                    raise Bo3RankingError(
                        "BO3.gg rejected the ranking request: "
                        f"{page_payload.get('message', page_payload['code'])}"
                    )
                page_payloads.append(page_payload)

            payload = dict(page_payloads[0])
            payload["data"] = [
                item
                for page_payload in page_payloads
                for item in page_payload.get("data", [])
                if isinstance(item, dict)
                and item.get("rank") is not None
                and item["rank"] <= RANKING_TEAMS_COUNT
            ]

        except httpx.HTTPStatusError as exc:
            raise Bo3RankingError(
                "BO3.gg ranking request failed: "
                f"HTTP {exc.response.status_code}; "
                f"response={exc.response.text[:300]!r}"
            ) from exc

        except (httpx.RequestError, ssl.SSLError) as exc:
            raise Bo3RankingError(
                "BO3.gg ranking request failed: "
                f"{type(exc).__name__}: {exc} "
                f"after {REQUEST_ATTEMPTS} attempts."
            ) from exc

        except ValueError as exc:
            raise Bo3RankingError(
                "BO3.gg returned invalid JSON."
            ) from exc

        try:
            result = Bo3RankingResponse(
                data=payload["data"],
                meta=payload["meta"],
                raw_payload=payload,
            )
        except (
                KeyError,
                ValidationError,
        ) as exc:
            raise Bo3RankingError(
                "BO3.gg ranking response has "
                "an unexpected format."
            ) from exc

        self._validate(result)

        return result



    @staticmethod
    def _latest_official_date(
        payload: Any,
    ) -> date:
        if not isinstance(payload, dict):
            raise Bo3RankingError(
                "BO3.gg official dates response "
                "has an unexpected format."
            )
        raw_dates = payload.get("data")
        if not isinstance(raw_dates, list) or not raw_dates:
            raise Bo3RankingError(
                "BO3.gg returned no official "
                "Valve ranking dates."
            )

        try:
            return max(
                date.fromisoformat(value)
                for value in raw_dates
                if isinstance(value, str)
            )
        except (
            ValueError,
            TypeError,
        ) as exc:
            raise Bo3RankingError(
                "BO3.gg returned an invalid "
                "official ranking date."
            ) from exc

    @staticmethod
    def _validate(
        result: Bo3RankingResponse,
    ) -> None:
        items = result.data
        if len(items) != RANKING_TEAMS_COUNT:
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                f"received {len(items)} teams."
            )

        ranks = sorted(item.rank for item in items)
        expected_ranks = list(
            range(1, RANKING_TEAMS_COUNT + 1)
        )
        if ranks != expected_ranks:
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                "ranks must be unique from 1 to 40."
            )

        team_ids = {item.team.id for item in items}
        slugs = {item.team.slug for item in items}
        if (
            len(team_ids) != RANKING_TEAMS_COUNT
            or len(slugs) != RANKING_TEAMS_COUNT
        ):
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                "duplicate team ID or slug."
            )

        if any(
            item.team_id != item.team.id
            for item in items
        ):
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                "ranking team IDs do not match."
            )

        ranking_dates = {
            item.ranking_date
            for item in items
        }
        if ranking_dates != {
            result.meta.ranking_date,
        }:
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                "ranking dates do not match."
            )

        if any(
                len(item.roster_players) != 5
                for item in items
        ):
            raise Bo3RankingError(
                "BO3.gg top-40 validation failed: "
                "every team must contain exactly 5 players."
            )
