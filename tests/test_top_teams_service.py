from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cs2eye.db.base import Base
from cs2eye.api.routers.teams import update_player_role
from cs2eye.api.schemas.teams import TeamParticipantRoleUpdate
from cs2eye.integrations.bo3.client import (
    Bo3RankingError,
    Bo3RankingResponse,
    Bo3PlayerResponse,
    Bo3PlayerTransfer,
    Bo3TeamResponse,
    Bo3TeamParticipant,
)
from cs2eye.models.team import (
    Player,
    RankingImportRun,
    Team,
    TeamParticipantMembership,
    TeamRankingSnapshot,
)
from cs2eye.services.top_teams_service import (
    TopTeamsService,
)
from tests.bo3_payloads import make_ranking_payload


class FakeRankingSource:
    source_url = "https://bo3.test/team_rankings"

    def __init__(
        self,
        response: Bo3RankingResponse,
    ) -> None:
        self._response = response

    async def fetch_top_teams(
        self,
    ) -> Bo3RankingResponse:
        return self._response

    async def fetch_team(
        self,
        team_id: int,
        slug: str,
    ) -> Bo3TeamResponse:
        players = [
            {
                "id": team_id * 100 + index,
                "slug": f"player-{team_id}-{index}",
                "nickname": f"Player {team_id}-{index}",
                "country": {"code": "EU", "name": "Europe"},
                "is_coach": False,
                "status": 1,
                "team_id": team_id,
            }
            for index in range(1, 6)
            if not (team_id == 1 and index == 1)
        ]
        players.append({
            "id": team_id * 100 + 99,
            "slug": f"coach-{team_id}",
            "nickname": f"Coach {team_id}",
            "country": {"code": "EU", "name": "Europe"},
            "is_coach": True,
            "status": 1,
            "team_id": team_id,
        })
        players.append({
            "id": team_id * 100 + 97,
            "slug": f"benched-{team_id}",
            "nickname": f"Benched {team_id}",
            "is_coach": False,
            "status": 2,
            "team_id": team_id,
        })
        players.append({
            "id": team_id * 100 + 98,
            "slug": f"substitute-{team_id}",
            "nickname": f"Substitute {team_id}",
            "country": {"code": "EU", "name": "Europe"},
            "is_coach": False,
            "status": 1,
            "team_id": team_id,
        })
        return Bo3TeamResponse(
            id=team_id,
            slug=slug,
            players=players,
            raw_payload={"id": team_id, "players": players},
        )

    async def fetch_player(
        self,
        player_id: int,
        slug: str,
    ) -> Bo3PlayerResponse:
        return Bo3PlayerResponse(
            id=player_id,
            slug=slug,
            nickname=f"Player {player_id}",
            country={"code": "EU", "name": "Europe"},
            six_month_avg_rating="6.5",
            updated_at="2026-07-25T05:07:17+00:00",
            raw_payload={},
        )


class FailingRankingSource:
    source_url = "https://bo3.test/team_rankings"

    async def fetch_top_teams(
        self,
    ) -> Bo3RankingResponse:
        raise Bo3RankingError(
            "BO3 test failure."
        )


def make_response(
    first_team_id: int,
) -> Bo3RankingResponse:
    payload = make_ranking_payload(
        first_team_id=first_team_id,
    )
    return Bo3RankingResponse(
        data=payload["data"],
        meta=payload["meta"],
        raw_payload=payload,
    )


def test_membership_dates_come_from_bo3_transfers() -> None:
    participant = Bo3TeamParticipant(
        id=17524,
        slug="karrigan",
        nickname="karrigan",
        player_transfers=[Bo3PlayerTransfer(
            player_id=17524,
            team_from_id=791,
            team_to_id=2713,
            action_date=date(2026, 4, 20),
            action_type=1,
        )],
    )
    joined_at = TopTeamsService._joined_at_from_bo3(2713, participant)
    left_at = TopTeamsService._left_at_from_bo3(
        2713,
        17524,
        [Bo3PlayerTransfer(
            player_id=17524,
            team_from_id=2713,
            team_to_id=793,
            action_date=date(2026, 7, 8),
            action_type=1,
        )],
    )

    assert joined_at == datetime(2026, 4, 20, tzinfo=UTC)
    assert left_at == datetime(2026, 7, 8, tzinfo=UTC)


def test_incomplete_bo3_transfers_are_ignored() -> None:
    participant = Bo3TeamParticipant(
        id=17524,
        slug="karrigan",
        nickname="karrigan",
        player_transfers=[Bo3PlayerTransfer()],
    )

    assert TopTeamsService._joined_at_from_bo3(2713, participant) is None
    assert TopTeamsService._left_at_from_bo3(
        2713,
        17524,
        [Bo3PlayerTransfer(player_id=None, action_date=None)],
    ) is None


async def test_team_details_fall_back_to_ranking_player() -> None:
    response = make_response(1)
    source = FakeRankingSource(response)
    service = TopTeamsService(None, source)  # type: ignore[arg-type]

    details = await service._fetch_team_details(response)

    roster = details[1].players
    assert [item.id for item in roster[:5]] == [
        101, 102, 103, 104, 105,
    ]
    assert roster[0].nickname == "Player 1-1"
    assert roster[0].is_substitute is False
    benched = next(item for item in roster if item.id == 197)
    assert benched.is_substitute is True


@pytest.fixture
async def session() -> (
    AsyncIterator[AsyncSession]
):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
        )

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_refresh_keeps_only_top_30_active_and_tracks_top_40(
    session: AsyncSession,
) -> None:
    first_run = await TopTeamsService(
        session,
        FakeRankingSource(make_response(1)),
    ).refresh()
    second_run = await TopTeamsService(
        session,
        FakeRankingSource(make_response(2)),
    ).refresh()

    active_result = await session.execute(
        select(Team)
        .where(
            Team.is_analytics_active.is_(True),
        )
        .order_by(Team.current_rank)
    )
    active_teams = list(active_result.scalars())
    old_team = (
        await session.execute(
            select(Team).where(
                Team.bo3_id == 1,
            )
        )
    ).scalar_one()
    snapshots_count = (
        await session.scalar(
            select(
                func.count(
                    TeamRankingSnapshot.id,
                )
            )
        )
    )

    assert first_run.status == "succeeded"
    assert first_run.teams_activated == 30
    assert second_run.teams_activated == 1
    assert second_run.teams_deactivated == 1
    assert len(active_teams) == 30
    assert active_teams[0].bo3_id == 2
    assert active_teams[-1].bo3_id == 31
    assert old_team.is_analytics_active is False
    assert old_team.current_rank is None
    shadow_ids = list((await session.execute(
        select(Team.bo3_id)
        .where(
            Team.is_analytics_active.is_(False),
            Team.current_rank.is_not(None),
        )
        .order_by(Team.current_rank)
    )).scalars())
    assert shadow_ids == list(range(32, 42))
    assert snapshots_count == 80


async def test_failed_refresh_keeps_active_top_30(
    session: AsyncSession,
) -> None:
    await TopTeamsService(
        session,
        FakeRankingSource(make_response(1)),
    ).refresh()

    with pytest.raises(
        Bo3RankingError,
        match="BO3 test failure",
    ):
        await TopTeamsService(
            session,
            FailingRankingSource(),
        ).refresh()

    active_ids = list(
        (
            await session.execute(
                select(Team.bo3_id)
                .where(
                    Team.is_analytics_active.is_(True),
                )
                .order_by(Team.current_rank)
            )
        ).scalars()
    )
    latest_run = (
        await session.execute(
            select(RankingImportRun)
            .order_by(
                RankingImportRun.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one()

    assert active_ids == list(range(1, 31))
    assert latest_run.status == "failed"
    assert (
        latest_run.error_message
        == "BO3 test failure."
    )


async def test_refresh_saves_rosters_and_is_idempotent(
    session: AsyncSession,
) -> None:
    source = FakeRankingSource(make_response(1))
    await TopTeamsService(session, source).refresh()
    await TopTeamsService(session, source).refresh()

    players_count = await session.scalar(
        select(func.count(Player.id)),
    )
    memberships_count = await session.scalar(
        select(func.count(TeamParticipantMembership.id)),
    )
    active_memberships_count = await session.scalar(
        select(func.count(TeamParticipantMembership.id)).where(
            TeamParticipantMembership.is_active.is_(True),
        ),
    )
    coaches_count = await session.scalar(
        select(func.count(TeamParticipantMembership.id)).where(
            TeamParticipantMembership.participant_type == "coach",
            TeamParticipantMembership.is_active.is_(True),
        ),
    )
    substitutes_count = await session.scalar(
        select(func.count(TeamParticipantMembership.id)).where(
            TeamParticipantMembership.participant_type == "substitute",
            TeamParticipantMembership.is_active.is_(True),
        ),
    )

    assert players_count == 320
    assert memberships_count == 320
    assert active_memberships_count == 320
    assert coaches_count == 40
    assert substitutes_count == 80
    latest_run = (
        await session.execute(
            select(RankingImportRun).order_by(RankingImportRun.id.desc()).limit(1)
        )
    ).scalar_one()
    assert latest_run.player_profiles_updated == 280
    assert latest_run.player_profiles_failed == 0


async def test_player_role_can_be_updated_manually(
    session: AsyncSession,
) -> None:
    team = Team(
        bo3_id=2713,
        bo3_slug="falcons-esports",
        name="Team Falcons",
        is_analytics_active=True,
    )
    player = Player(
        bo3_id=17524,
        bo3_slug="karrigan",
        nickname="karrigan",
        is_analytics_active=True,
    )
    session.add_all([team, player])
    await session.flush()
    membership = TeamParticipantMembership(
        team_id=team.id,
        player_id=player.id,
        participant_type="player",
        is_active=True,
    )
    session.add(membership)
    await session.commit()

    response = await update_player_role(
        team.id,
        player.id,
        TeamParticipantRoleUpdate(role="igl"),
        session,
    )

    assert membership.role == "igl"
    assert response.roster[0].role == "igl"
    assert "igl" not in response.strength.missing_required_roles
