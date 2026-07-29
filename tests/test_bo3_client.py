import ssl

import httpx
import pytest

from cs2eye.integrations.bo3.client import (
    Bo3Client,
    Bo3RankingError,
)
from tests.bo3_payloads import make_ranking_payload


def make_http_client(
    payload: dict,
) -> httpx.AsyncClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert (
            request.url.params[
                "filter[discipline_id][eq]"
            ]
            == "1"
        )
        assert (
            request.url.params[
                "pagination[per_page]"
            ]
            == "30"
        )
        assert request.url.params["scope"] == "cs2"
        page = int(request.url.params["page"])
        page_payload = dict(payload)
        page_payload["data"] = [
            item for item in payload["data"]
            if (page - 1) * 30 < item["rank"] <= page * 30
        ]
        page_payload["meta"] = dict(payload["meta"])
        page_payload["meta"]["current_page"] = page
        page_payload["meta"]["per_page"] = 30
        return httpx.Response(
            200,
            json=page_payload,
            request=request,
        )

    return httpx.AsyncClient(
        base_url="https://api.bo3.gg/api/v2",
        transport=httpx.MockTransport(handler),
    )


async def test_client_accepts_valid_top_40() -> None:
    async with make_http_client(
        make_ranking_payload(),
    ) as http_client:
        ranking = await Bo3Client(
            http_client,
        ).fetch_top_teams()

    assert len(ranking.data) == 40
    assert ranking.data[0].rank == 1
    assert ranking.data[-1].rank == 40
    assert len(
        ranking.data[0].roster_players,
    ) == 5


async def test_client_rejects_less_than_40() -> None:
    async with make_http_client(
        make_ranking_payload(
            teams_count=39,
        ),
    ) as http_client:
        with pytest.raises(
            Bo3RankingError,
            match="received 39 teams",
        ):
            await Bo3Client(
                http_client,
            ).fetch_top_teams()


async def test_client_rejects_duplicate_team() -> None:
    payload = make_ranking_payload()
    payload["data"][39]["team"] = (
        payload["data"][0]["team"]
    )

    async with make_http_client(
        payload,
    ) as http_client:
        with pytest.raises(
            Bo3RankingError,
            match="duplicate team ID or slug",
        ):
            await Bo3Client(
                http_client,
            ).fetch_top_teams()


async def test_client_accepts_players_and_coach() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "id": 2713,
            "slug": "falcons-esports",
            "players": [
                {
                    "id": index,
                    "slug": f"participant-{index}",
                    "nickname": f"Participant {index}",
                    "is_coach": index == 6,
                }
                for index in range(1, 7)
            ],
        }
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as http_client:
        team = await Bo3Client(http_client).fetch_team(
            2713,
            "falcons-esports",
        )

    assert len(team.players) == 6
    assert sum(item.is_coach for item in team.players) == 1


async def test_client_accepts_null_coach_flag() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "id": 736,
            "slug": "the-mongolz",
            "players": [{
                "id": 84771,
                "slug": "darkmeister",
                "nickname": "DarkMeister",
                "is_coach": None,
            }],
        }
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as http_client:
        team = await Bo3Client(http_client).fetch_team(
            736,
            "the-mongolz",
        )

    assert team.players[0].is_coach is None


async def test_team_request_retries_connect_timeout() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectTimeout("temporary timeout", request=request)
        return httpx.Response(
            200,
            json={
                "id": 736,
                "slug": "the-mongolz",
                "players": [{
                    "id": 84771,
                    "slug": "darkmeister",
                    "nickname": "DarkMeister",
                }],
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as http_client:
        team = await Bo3Client(http_client).fetch_team(736, "the-mongolz")

    assert team.id == 736
    assert attempts == 3


async def test_ranking_request_retries_low_level_ssl_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    payload = make_ranking_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ssl.SSLError("record layer failure")
        page = int(request.url.params["page"])
        page_payload = dict(payload)
        page_payload["data"] = [
            item for item in payload["data"]
            if (page - 1) * 30 < item["rank"] <= page * 30
        ]
        return httpx.Response(200, json=page_payload, request=request)

    async def no_delay(_: float) -> None:
        return None

    monkeypatch.setattr(
        "cs2eye.integrations.bo3.client.asyncio.sleep",
        no_delay,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as http_client:
        ranking = await Bo3Client(http_client).fetch_top_teams()

    assert len(ranking.data) == 40
    assert attempts == 4
