from datetime import datetime
from time import monotonic
from typing import Any

import httpx


class CS2EyeAPIError(RuntimeError):
    """A backend request failed or returned an invalid response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CS2EyeNotFoundError(CS2EyeAPIError):
    pass


class CS2EyeAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        generation_timeout: float = 330.0,
        client: httpx.AsyncClient | None = None,
        tournaments_ttl: float = 60.0,
        tournament_matches_ttl: float = 45.0,
    ) -> None:
        self._generation_timeout = generation_timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout,
        )
        self._tournaments_ttl = tournaments_ttl
        self._tournament_matches_ttl = tournament_matches_ttl
        self._tournaments_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._tournament_matches_cache: dict[
            int, tuple[float, list[dict[str, Any]]]
        ] = {}

    async def __aenter__(self) -> "CS2EyeAPIClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        try:
            kwargs: dict[str, Any] = {"params": params, "json": json}
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            exception = CS2EyeNotFoundError if error.response.status_code == 404 else CS2EyeAPIError
            raise exception(
                f"{method} {path} failed: {error}",
                status_code=error.response.status_code,
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise CS2EyeAPIError(f"{method} {path} failed: {error}") from error

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(
        self, path: str, *, json: dict[str, Any], timeout: float | None = None,
    ) -> Any:
        return await self._request("POST", path, json=json, timeout=timeout)

    async def get_tournaments(self) -> list[dict[str, Any]]:
        now = monotonic()
        if self._tournaments_cache is not None:
            expires_at, items = self._tournaments_cache
            if now < expires_at:
                return items
        payload = await self._get("/api/v1/tournaments")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise CS2EyeAPIError("Invalid tournaments response")
        items = payload["items"]
        self._tournaments_cache = (now + self._tournaments_ttl, items)
        return items

    async def get_tournament_matches(self, tournament_id: int) -> list[dict[str, Any]]:
        now = monotonic()
        cached = self._tournament_matches_cache.get(tournament_id)
        if cached is not None and now < cached[0]:
            return cached[1]
        payload = await self._get(f"/api/v1/tournaments/{tournament_id}/matches")
        if not isinstance(payload, list):
            raise CS2EyeAPIError("Invalid tournament matches response")
        self._tournament_matches_cache[tournament_id] = (
            now + self._tournament_matches_ttl, payload,
        )
        return payload

    async def get_tournament(self, tournament_id: int) -> dict[str, Any]:
        payload = await self._get(f"/api/v1/tournaments/{tournament_id}")
        if not isinstance(payload, dict):
            raise CS2EyeAPIError("Invalid tournament response")
        return payload

    async def get_match(self, match_id: int) -> dict[str, Any]:
        payload = await self._get(f"/api/v1/matches/{match_id}")
        if not isinstance(payload, dict):
            raise CS2EyeAPIError("Invalid match response")
        return payload

    async def get_match_analysis_context(
        self,
        *,
        team_a_id: int,
        team_b_id: int,
        as_of: datetime,
        match_id: int,
        tournament_id: int | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "team_a_id": team_a_id,
            "team_b_id": team_b_id,
            "as_of": as_of.isoformat(),
            "match_id": match_id,
            "analysis_mode": "pre_match",
        }
        if tournament_id is not None:
            params["tournament_id"] = tournament_id
        payload = await self._get("/api/v1/analysis/match-analysis-context", params=params)
        if not isinstance(payload, dict):
            raise CS2EyeAPIError("Invalid match analysis context response")
        return payload

    async def get_match_maps_veto(self, **kwargs: Any) -> dict[str, Any]:
        context = await self.get_match_analysis_context(**kwargs)
        return {"veto": context.get("veto"), "map_matchups": context.get("map_matchups")}

    async def get_match_form(self, **kwargs: Any) -> dict[str, Any]:
        context = await self.get_match_analysis_context(**kwargs)
        return {"match": context.get("match"), "teams": context.get("teams")}

    async def get_match_h2h(self, **kwargs: Any) -> dict[str, Any]:
        context = await self.get_match_analysis_context(**kwargs)
        return {"teams": context.get("teams"), "h2h": context.get("h2h")}

    async def get_match_rosters(self, **kwargs: Any) -> dict[str, Any]:
        context = await self.get_match_analysis_context(**kwargs)
        return {"teams": context.get("teams")}

    async def get_latest_llm_analysis(
        self, *, team_a_id: int, team_b_id: int, match_id: int,
    ) -> dict[str, Any]:
        payload = await self._get(
            "/api/v1/analysis/llm-match-analysis/latest",
            params={
                "team_a_id": team_a_id, "team_b_id": team_b_id,
                "match_id": match_id, "analysis_mode": "pre_match",
            },
        )
        return self._stored_analysis(payload)

    async def generate_llm_analysis(
        self, *, team_a_id: int, team_b_id: int, as_of: datetime,
        match_id: int, tournament_id: int | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "team_a_id": team_a_id, "team_b_id": team_b_id,
            "as_of": as_of.isoformat(), "match_id": match_id,
            "analysis_mode": "pre_match", "language": "ru",
        }
        if tournament_id is not None:
            body["tournament_id"] = tournament_id
        return self._stored_analysis(await self._post(
            "/api/v1/analysis/llm-match-analysis/generate", json=body,
            timeout=self._generation_timeout,
        ))

    async def get_llm_analysis_history(
        self, *, match_id: int, limit: int = 50,
    ) -> list[dict[str, Any]]:
        payload = await self._get(
            "/api/v1/analysis/llm-match-analysis/history",
            params={"match_id": match_id, "limit": limit, "offset": 0},
        )
        if not isinstance(payload, list):
            raise CS2EyeAPIError("Invalid LLM analysis history response")
        return payload

    async def get_llm_analysis_run(self, analysis_run_id: int) -> dict[str, Any]:
        return self._stored_analysis(await self._get(
            f"/api/v1/analysis/llm-match-analysis/{analysis_run_id}",
        ))

    async def regenerate_llm_analysis(self, analysis_run_id: int) -> dict[str, Any]:
        return self._stored_analysis(await self._post(
            f"/api/v1/analysis/llm-match-analysis/{analysis_run_id}/regenerate",
            json={"reuse_context": True, "reuse_explanation_plan": False},
            timeout=self._generation_timeout,
        ))

    @staticmethod
    def _stored_analysis(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("analysis_run_id"), int):
            raise CS2EyeAPIError("Invalid stored LLM analysis response")
        return payload
