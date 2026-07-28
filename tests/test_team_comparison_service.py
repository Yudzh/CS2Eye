from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.team import Player, Team, TeamParticipantMembership
from cs2eye.services.team_comparison_service import (
    InactiveTeamError,
    SameTeamComparisonError,
    TeamComparisonService,
)
from cs2eye.services.team_strength_service import TeamStrength


NOW = datetime(2026, 7, 26, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


def strength(score: float) -> TeamStrength:
    return TeamStrength(
        active_players_count=5,
        base_player_score=score,
        roster_bonus=0,
        roster_penalty=0,
        total_adjustment=0,
        score_before_limits=score,
        team_strength_score=score,
        calculation=f"{score:.2f} + 0.00 - 0.00 = {score:.2f}",
        missing_required_roles=[],
        factors=[],
        notes=[],
    )


async def add_team(
    session: AsyncSession,
    team_id: int,
    name: str,
    *,
    active: bool = True,
    rank: int = 1,
    points: str = "1000",
    awper_strength: int | None = 80,
) -> Team:
    team = Team(
        id=team_id,
        bo3_id=team_id * 10,
        bo3_slug=name.lower().replace(" ", "-"),
        name=name,
        is_analytics_active=active,
        current_rank=rank,
        current_points=Decimal(points),
        ranking_date=date(2026, 7, 20),
        roster_synced_at=NOW - timedelta(days=1),
    )
    session.add(team)
    roles = ["awper", "igl", "entry_frag", "lurk", "anchor_support"]
    for index, role in enumerate(roles, 1):
        player_id = team_id * 100 + index
        player = Player(
            id=player_id,
            bo3_id=player_id * 10,
            bo3_slug=f"p-{player_id}",
            nickname=f"{name}-{role}",
            player_strength=awper_strength if role == "awper" else 60,
            bo3_rating=Decimal("6.5"),
        )
        session.add(player)
        session.add(TeamParticipantMembership(
            team_id=team_id,
            player_id=player_id,
            participant_type="player",
            role=role,
            is_active=True,
            joined_at=NOW - timedelta(days=100),
        ))
    await session.commit()
    return team


@pytest.mark.parametrize(
    ("score_a", "score_b", "winner", "difference", "relative_a", "relative_b"),
    [
        (70, 60, 1, 10, 53.85, 46.15),
        (64, 60, None, 4, 51.61, 48.39),
        (65, 60, 1, 5, 52.0, 48.0),
    ],
)
async def test_strength_advantage_and_relative_percentages(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    score_a: float,
    score_b: float,
    winner: int | None,
    difference: float,
    relative_a: float,
    relative_b: float,
) -> None:
    await add_team(session, 1, "Team A", rank=3)
    await add_team(session, 2, "Team B", rank=7)

    def fake_strength(roster: list[tuple[Player, TeamParticipantMembership]], **_: object):
        return strength(score_a if roster[0][1].team_id == 1 else score_b)

    monkeypatch.setattr(
        "cs2eye.services.team_comparison_service.calculate_team_strength",
        fake_strength,
    )
    result = await TeamComparisonService(session, now=NOW).compare(1, 2)

    assert result.strength_advantage_team_id == winner
    assert result.strength_advantage_diff == difference
    assert result.team_a.relative_strength_percent == relative_a
    assert result.team_b.relative_strength_percent == relative_b


async def test_same_team_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(SameTeamComparisonError, match="две разные"):
        await TeamComparisonService(session).compare(1, 1)


async def test_inactive_team_is_rejected(session: AsyncSession) -> None:
    await add_team(session, 1, "Team A")
    await add_team(session, 2, "Old Team", active=False)
    with pytest.raises(InactiveTeamError, match="активный Top-30"):
        await TeamComparisonService(session).compare(1, 2)


async def test_only_current_players_take_part(session: AsyncSession) -> None:
    await add_team(session, 1, "Team A")
    await add_team(session, 2, "Team B")
    extras = [
        ("coach", True, None),
        ("substitute", True, None),
        ("player", False, None),
        ("player", True, NOW),
    ]
    for index, (participant_type, active, left_at) in enumerate(extras, 90):
        player_id = 1000 + index
        session.add(Player(
            id=player_id,
            bo3_id=player_id * 10,
            bo3_slug=f"extra-{index}",
            nickname=f"Extra {index}",
            player_strength=100,
        ))
        session.add(TeamParticipantMembership(
            team_id=1,
            player_id=player_id,
            participant_type=participant_type,
            is_active=active,
            left_at=left_at,
        ))
    await session.commit()

    result = await TeamComparisonService(session, now=NOW).compare(1, 2)

    assert len(result.team_a.roster) == 5
    assert len(result.team_a.coaches) == 1
    assert all(player.nickname.startswith("Team A") for player in result.team_a.roster)


async def test_role_comparison_and_missing_role_fallback(
    session: AsyncSession,
) -> None:
    await add_team(session, 1, "Team A", awper_strength=80)
    await add_team(session, 2, "Team B", awper_strength=72)
    result = await TeamComparisonService(session, now=NOW).compare(1, 2)
    awper = result.role_comparisons[1]
    assert awper.role == "awper"
    assert awper.advantage_team_id == 1
    assert awper.advantage_diff == 8

    awper_b = next(player for player in result.team_b.roster if player.role == "awper")
    membership = (
        await session.execute(
            select(TeamParticipantMembership).where(
                TeamParticipantMembership.player_id == awper_b.id,
                TeamParticipantMembership.team_id == 2,
            )
        )
    ).scalar_one()
    assert membership is not None
    membership.role = None
    await session.commit()
    missing = await TeamComparisonService(session, now=NOW).compare(1, 2)
    missing_awper = missing.role_comparisons[1]
    assert missing_awper.team_b_score is None
    assert missing_awper.advantage_team_id is None
    assert missing_awper.advantage_diff is None


async def test_missing_player_strength_uses_fifty(session: AsyncSession) -> None:
    await add_team(session, 1, "Team A", awper_strength=None)
    await add_team(session, 2, "Team B")
    result = await TeamComparisonService(session, now=NOW).compare(1, 2)
    awper = next(player for player in result.team_a.roster if player.role == "awper")
    assert awper.role == "awper"
    assert awper.player_strength is None
    assert awper.effective_player_strength == 50
    assert awper.strength_is_fallback is True


async def test_ranking_advantage(session: AsyncSession) -> None:
    await add_team(session, 1, "Team A", rank=3)
    await add_team(session, 2, "Team B", rank=7)
    result = await TeamComparisonService(session, now=NOW).compare(1, 2)
    assert result.ranking.rank_advantage_team_id == 1
    assert result.ranking.rank_difference == 4


async def test_compare_api_contract(session: AsyncSession) -> None:
    await add_team(session, 1, "Team A", rank=3)
    await add_team(session, 2, "Team B", rank=7)
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/teams/compare",
            params={"team_a_id": 1, "team_b_id": 2},
        )
        same = await client.get(
            "/api/v1/teams/compare",
            params={"team_a_id": 1, "team_b_id": 1},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["team_a"]["strength"]["team_strength_score"] is not None
    assert [item["role"] for item in payload["role_comparisons"]] == [
        "igl", "awper", "entry_frag", "lurk", "anchor_support", "rifler",
    ]
    assert same.status_code == 400
    assert same.json()["detail"] == "Выберите две разные команды."
