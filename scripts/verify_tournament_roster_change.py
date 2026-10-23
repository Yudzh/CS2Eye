"""Exercise real BO3 + API against configured PostgreSQL, then roll back all rows.

Run: DEBUG=false PYTHONPATH=src .venv/bin/python scripts/verify_tournament_roster_change.py
The HTTP calls run the local application's actual routes through ASGI. They do not
call a separately deployed API: its commits could not share this rollback scope.
"""
import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import AsyncSessionLocal, engine, get_db_session
from cs2eye.integrations.bo3.client import Bo3Client
from cs2eye.main import create_app
from cs2eye.models.match import Tournament, TournamentRosterCheck, TournamentTeam
from cs2eye.models.team import Player, Team
from cs2eye.services.team_roster_service import set_current_roster
from cs2eye.services.tournament_lineup_monitor import select_roster_players


async def main():
    # Pick real data, without changing it, before opening the rollback scope.
    async with AsyncSessionLocal() as session:
        team = await session.scalar(select(Team).where(Team.bo3_slug == "1win"))
        if team is None:
            raise RuntimeError("This verification requires the existing 1win team")
        original_roster_id = team.current_roster_id
        async with Bo3Client() as client:
            detail = await client.fetch_team(team.bo3_id, team.bo3_slug)
        selected = select_roster_players(detail)
        if len(selected) != 5:
            raise RuntimeError("BO3 did not return a complete five; no stub applied")
        players = list((await session.scalars(select(Player).where(
            Player.bo3_id.in_([p.id for p in selected])))).all())
        if len(players) != 5:
            raise RuntimeError("BO3 players must already exist locally for this verification")
        by_bo3 = {p.bo3_id: p for p in players}
        real_players = [by_bo3[p.id] for p in selected]
        outgoing = real_players[-1]
        stub = await session.scalar(select(Player).where(
            Player.nickname == "ZywOo", Player.id.not_in([p.id for p in players])))
        if stub is None:
            raise RuntimeError("An existing ZywOo outside this roster is required")
        team_id = team.id
        actual_ids = {p.id for p in real_players}
        expected_baseline = actual_ids - {outgoing.id} | {stub.id}
        original_count = await session.scalar(select(func.count()).select_from(TournamentRosterCheck))

    tournament_id = None
    calls = 0
    original_fetch = Bo3Client.fetch_team

    async def counted_fetch(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return await original_fetch(self, *args, **kwargs)

    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            # Endpoint session.commit() releases a savepoint, never the outer transaction.
            async with AsyncSession(bind=connection, expire_on_commit=False,
                                    join_transaction_mode="create_savepoint") as session:
                tournament = Tournament(name=f"Roster rollback verification {uuid4().hex}",
                    year=datetime.now(UTC).year, start_date=datetime.now(UTC).date(),
                    end_date=datetime.now(UTC).date())
                session.add(tournament)
                await session.flush()
                tournament_id = tournament.id
                session.add(TournamentTeam(tournament_id=tournament_id, team_id=team_id))
                await set_current_roster(session, team_id, real_players[:-1] + [stub], source="manual")
                await session.commit()
                assert outer.is_active

                app = create_app()

                async def database_override():
                    yield session

                app.dependency_overrides[get_db_session] = database_override
                prefix = f"/api/v1/tournaments/{tournament_id}/teams/{team_id}"
                with patch.object(Bo3Client, "fetch_team", counted_fetch):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                                 base_url="http://verification", timeout=60) as client:
                        first = await client.post(prefix + "/roster-overrides/check")
                        first.raise_for_status()
                        assert outer.is_active
                        assert first.json()["status"] == "changed", first.text
                        assert first.json()["added_ids"] == [outgoing.id], first.text
                        assert first.json()["missing_ids"] == [stub.id], first.text
                        saved = await client.get(prefix + "/effective-roster")
                        saved.raise_for_status()
                        data = saved.json()
                        assert {p["id"] for p in data["players"]} == actual_ids
                        assert {p["id"] for p in data["roster_check"]["baseline"]} == expected_baseline
                        assert data["stand_in_penalty"] == 0
                        second = await client.post(prefix + "/roster-overrides/check")
                        second.raise_for_status()
                        assert second.json()["created"] == 0, second.text
                        assert calls == 1, calls
                        assert await session.scalar(select(func.count()).select_from(
                            TournamentRosterCheck).where(
                                TournamentRosterCheck.tournament_id == tournament_id)) == 1
                print({"team": team.name, "stub": f"{stub.nickname} instead of {outgoing.nickname}",
                       "status": first.json()["status"], "added": outgoing.nickname,
                       "missing": stub.nickname, "penalty": data["stand_in_penalty"],
                       "repeat": "no duplicate, no second BO3 request", "BO3_requests": calls})
        finally:
            await outer.rollback()

    async with AsyncSessionLocal() as session:
        assert await session.get(Tournament, tournament_id) is None
        current = await session.get(Team, team_id)
        assert current.current_roster_id == original_roster_id
        assert await session.scalar(select(func.count()).select_from(TournamentRosterCheck)) == original_count
    print("ROLLBACK VERIFIED: temporary tournament/check removed; original main roster restored.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
