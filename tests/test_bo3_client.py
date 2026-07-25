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
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    return httpx.AsyncClient(
        base_url="https://api.bo3.gg/api/v2",
        transport=httpx.MockTransport(handler),
    )


async def test_client_accepts_valid_top_30() -> None:
    async with make_http_client(
        make_ranking_payload(),
    ) as http_client:
        ranking = await Bo3Client(
            http_client,
        ).fetch_top_teams()

    assert len(ranking.data) == 30
    assert ranking.data[0].rank == 1
    assert ranking.data[-1].rank == 30
    assert len(
        ranking.data[0].roster_players,
    ) == 5


async def test_client_rejects_less_than_30() -> None:
    async with make_http_client(
        make_ranking_payload(
            teams_count=29,
        ),
    ) as http_client:
        with pytest.raises(
            Bo3RankingError,
            match="received 29 teams",
        ):
            await Bo3Client(
                http_client,
            ).fetch_top_teams()


async def test_client_rejects_duplicate_team() -> None:
    payload = make_ranking_payload()
    payload["data"][29]["team"] = (
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
