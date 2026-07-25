import asyncio
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.integrations.bo3.client import (
    Bo3Client,
    Bo3Country,
    Bo3RankingError,
    Bo3RankingResponse,
    Bo3TeamParticipant,
    Bo3TeamResponse,
    Bo3PlayerResponse,
)
from cs2eye.services.player_service import apply_player_profile
from cs2eye.models.team import (
    Player,
    RankingImportRun,
    Team,
    TeamParticipantMembership,
    TeamRankingSnapshot,
)


class RankingSource(Protocol):
    @property
    def source_url(self) -> str: ...

    async def fetch_top_teams(
        self,
    ) -> Bo3RankingResponse: ...

    async def fetch_team(
        self,
        team_id: int,
        slug: str,
    ) -> Bo3TeamResponse: ...

    async def fetch_player(
        self,
        player_id: int,
        slug: str,
    ) -> Bo3PlayerResponse: ...


class TopTeamsService:
    def __init__(
        self,
        session: AsyncSession,
        source: RankingSource | None = None,
    ) -> None:
        self._session = session
        self._owned_source = Bo3Client() if source is None else None
        self._source = source or self._owned_source

    async def probe(self) -> Bo3RankingResponse:
        return await self._source.fetch_top_teams()

    async def refresh(self) -> RankingImportRun:
        run = RankingImportRun(
            status="running",
            source_url=self._source.source_url,
        )
        self._session.add(run)
        await self._session.commit()
        run_id = run.id

        try:
            ranking = await self._source.fetch_top_teams()
            team_details = await self._fetch_team_details(
                ranking,
            )
            await self._apply_ranking(
                run_id,
                ranking,
                team_details,
            )
            await self._refresh_player_profiles(run_id)
        except Exception as exc:
            await self._session.rollback()
            await self._mark_failed(
                run_id,
                str(exc),
            )
            raise
        finally:
            if self._owned_source is not None:
                await self._owned_source.aclose()

        refreshed_run = await self._session.get(
            RankingImportRun,
            run_id,
        )
        if refreshed_run is None:
            raise RuntimeError(
                "Import run disappeared after refresh."
            )
        return refreshed_run

    async def _refresh_player_profiles(self, run_id: int) -> None:
        result = await self._session.execute(
            select(Player)
            .join(
                TeamParticipantMembership,
                TeamParticipantMembership.player_id == Player.id,
            )
            .where(
                Player.is_analytics_active.is_(True),
                TeamParticipantMembership.is_active.is_(True),
                TeamParticipantMembership.participant_type != "coach",
            )
        )
        players = list({
            player.id: player
            for player in result.scalars()
        }.values())
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(player: Player):
            async with semaphore:
                try:
                    profile = await self._source.fetch_player(player.bo3_id, player.bo3_slug)
                    return player.id, profile, None
                except Exception as exc:
                    return player.id, None, {
                        "id": player.id,
                        "bo3_id": player.bo3_id,
                        "bo3_slug": player.bo3_slug,
                        "nickname": player.nickname,
                        "error": f"{type(exc).__name__}: {exc}"[:500],
                    }

        fetched = await asyncio.gather(*(fetch_one(player) for player in players))
        profiles: dict[int, Bo3PlayerResponse] = {
            player_id: profile
            for player_id, profile, _ in fetched
            if profile is not None
        }
        failures = [
            failure
            for _, _, failure in fetched
            if failure is not None
        ]
        synced_at = datetime.now(UTC)
        run = await self._session.get(RankingImportRun, run_id)
        if run is None:
            raise RuntimeError("Import run does not exist.")
        for player in players:
            profile = profiles.get(player.id)
            if profile is not None:
                apply_player_profile(player, profile, synced_at)
        run.player_profiles_updated = len(profiles)
        run.player_profiles_failed = len(players) - len(profiles)
        run.player_profile_failures = failures
        await self._session.commit()

    async def _fetch_team_details(
        self,
        ranking: Bo3RankingResponse,
    ) -> dict[int, Bo3TeamResponse]:
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(
            team_id: int,
            slug: str,
        ) -> Bo3TeamResponse:
            async with semaphore:
                return await self._source.fetch_team(
                    team_id,
                    slug,
                )

        details = await asyncio.gather(*(
            fetch_one(item.team.id, item.team.slug)
            for item in ranking.data
        ))
        details_by_id = {detail.id: detail for detail in details}
        for item in ranking.data:
            detail = details_by_id[item.team.id]
            ranked_player_ids = [
                player.id for player in item.roster_players
            ]
            if (
                any(player_id is None for player_id in ranked_player_ids)
                or len(set(ranked_player_ids)) != 5
            ):
                raise Bo3RankingError(
                    "BO3.gg ranking roster must contain five "
                    f"unique player IDs for {item.team.slug}."
                )
            participants_by_id = {
                participant.id: participant
                for participant in detail.players
            }
            coaches = [
                participant for participant in detail.players
                if participant.is_coach
                and participant.status == 1
                and participant.team_id == detail.id
            ]
            main_players: list[Bo3TeamParticipant] = []
            for ranked_player in item.roster_players:
                if ranked_player.id is None:
                    continue
                participant = participants_by_id.get(
                    ranked_player.id,
                )
                if participant is None:
                    participant = Bo3TeamParticipant(
                        id=ranked_player.id,
                        slug=(
                            ranked_player.slug
                            or f"player-{ranked_player.id}"
                        ),
                        nickname=ranked_player.nickname,
                        image_url=ranked_player.image_url,
                        country=Bo3Country(
                            code=ranked_player.country_code,
                        ),
                        is_coach=False,
                    )
                main_players.append(participant)
            main_ids = {participant.id for participant in main_players}
            substitutes = [
                participant for participant in detail.players
                if not participant.is_coach
                and participant.id not in main_ids
                and participant.team_id == detail.id
            ]
            for participant in substitutes:
                participant.is_substitute = True
            detail.players = main_players + substitutes + coaches
        return details_by_id

    async def _apply_ranking(
        self,
        run_id: int,
        ranking: Bo3RankingResponse,
        team_details: dict[int, Bo3TeamResponse],
    ) -> None:
        synced_at = datetime.now(UTC)
        async with self._session.begin():
            run = await self._session.get(
                RankingImportRun,
                run_id,
                with_for_update=True,
            )
            if run is None:
                raise RuntimeError(
                    "Import run does not exist."
                )

            active_result = await self._session.execute(
                select(Team).where(
                    Team.is_analytics_active.is_(True),
                )
            )
            previously_active = {
                team.bo3_id: team
                for team in active_result.scalars()
            }
            incoming_ids = {
                item.team.id
                for item in ranking.data
            }
            deactivated = 0
            for bo3_id, team in previously_active.items():
                if bo3_id not in incoming_ids:
                    team.is_analytics_active = False
                    team.current_rank = None
                    team.current_points = None
                    team.rank_change = None
                    team.ranking_date = (
                        ranking.meta.ranking_date
                    )
                    deactivated += 1

            activated = 0
            player_result = await self._session.execute(
                select(Player)
            )
            players_by_bo3_id = {
                player.bo3_id: player
                for player in player_result.scalars()
            }
            membership_result = await self._session.execute(
                select(
                    TeamParticipantMembership,
                    Team.bo3_id,
                    Player.bo3_id,
                )
                .join(
                    Team,
                    Team.id == TeamParticipantMembership.team_id,
                )
                .join(
                    Player,
                    Player.id == TeamParticipantMembership.player_id,
                )
                .where(
                    TeamParticipantMembership.is_active.is_(True),
                )
            )
            active_memberships = {
                (team_bo3_id, player_bo3_id): membership
                for membership, team_bo3_id, player_bo3_id
                in membership_result.all()
            }
            incoming_memberships = {
                (detail.id, participant.id)
                for detail in team_details.values()
                for participant in detail.players
            }
            for key, membership in active_memberships.items():
                if key not in incoming_memberships:
                    membership.is_active = False
                    membership.left_at = synced_at

            for player in players_by_bo3_id.values():
                player.is_analytics_active = False

            for detail in team_details.values():
                for participant in detail.players:
                    player = players_by_bo3_id.get(participant.id)
                    if player is None:
                        player = Player(
                            bo3_id=participant.id,
                            bo3_slug=participant.slug,
                            nickname=participant.nickname,
                        )
                        self._session.add(player)
                        players_by_bo3_id[player.bo3_id] = player
                    country = participant.country
                    player.bo3_slug = participant.slug
                    player.nickname = participant.nickname
                    player.image_url = participant.image_url
                    player.country_code = (
                        country.code if country else None
                    )
                    player.country_name = (
                        country.name if country else None
                    )
                    player.is_analytics_active = True

            await self._session.flush()

            for item in sorted(
                ranking.data,
                key=lambda value: value.rank,
            ):
                result = await self._session.execute(
                    select(Team).where(
                        Team.bo3_id == item.team.id,
                    )
                )
                team = result.scalar_one_or_none()
                if team is None:
                    team = Team(
                        bo3_id=item.team.id,
                        bo3_slug=item.team.slug,
                        name=item.team.name,
                    )
                    self._session.add(team)
                    activated += 1
                elif not team.is_analytics_active:
                    activated += 1

                country = item.team.country
                team.bo3_slug = item.team.slug
                team.name = item.team.name
                team.logo_url = item.team.image_url
                team.country_code = (
                    country.code if country else None
                )
                team.country_name = (
                    country.name if country else None
                )
                team.region = item.region
                team.current_rank = item.rank
                team.current_points = item.score
                team.rank_change = item.rank_diff
                team.ranking_date = item.ranking_date
                team.is_analytics_active = True
                team.roster_synced_at = synced_at

                await self._session.flush()
                detail = team_details[item.team.id]
                for participant in detail.players:
                    player = players_by_bo3_id[participant.id]

                    membership = active_memberships.get(
                        (team.bo3_id, player.bo3_id),
                    )
                    if participant.is_coach:
                        participant_type = "coach"
                    elif participant.is_substitute:
                        participant_type = "substitute"
                    else:
                        participant_type = "player"
                    if membership is None:
                        membership = TeamParticipantMembership(
                            team_id=team.id,
                            player_id=player.id,
                            participant_type=participant_type,
                            joined_at=synced_at,
                        )
                        self._session.add(membership)
                        active_memberships[
                            (team.bo3_id, player.bo3_id)
                        ] = membership
                    else:
                        membership.participant_type = participant_type
                self._session.add(
                    TeamRankingSnapshot(
                        import_run_id=run.id,
                        team_id=team.id,
                        ranking_date=item.ranking_date,
                        rank=item.rank,
                        points=item.score,
                        rank_change=item.rank_diff,
                        roster_payload=[
                            player.model_dump(
                                mode="json",
                            )
                            for player
                            in item.roster_players
                        ],
                    )
                )

            run.status = "succeeded"
            run.finished_at = synced_at
            run.ranking_date = ranking.meta.ranking_date
            run.teams_received = len(ranking.data)
            run.teams_activated = activated
            run.teams_deactivated = deactivated
            run.error_message = None
            run.source_payload = ranking.raw_payload

    async def _mark_failed(
        self,
        run_id: int,
        error_message: str,
    ) -> None:
        async with self._session.begin():
            run = await self._session.get(
                RankingImportRun,
                run_id,
            )
            if run is None:
                return
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_message = error_message[:2000]


async def list_active_teams(
    session: AsyncSession,
) -> list[Team]:
    result = await session.execute(
        select(Team)
        .where(
            Team.is_analytics_active.is_(True),
        )
        .order_by(Team.current_rank.asc())
    )
    return list(result.scalars())


async def list_active_rosters(
    session: AsyncSession,
) -> dict[int, list[tuple[Player, str]]]:
    result = await session.execute(
        select(
            TeamParticipantMembership.team_id,
            Player,
            TeamParticipantMembership.participant_type,
        )
        .join(
            Player,
            Player.id == TeamParticipantMembership.player_id,
        )
        .where(
            TeamParticipantMembership.is_active.is_(True),
        )
        .order_by(
            TeamParticipantMembership.participant_type.desc(),
            Player.nickname.asc(),
        )
    )
    rosters: dict[int, list[tuple[Player, str]]] = {}
    for team_id, player, participant_type in result.all():
        rosters.setdefault(team_id, []).append(
            (player, participant_type),
        )
    return rosters


async def get_latest_import_run(
    session: AsyncSession,
) -> RankingImportRun | None:
    result = await session.execute(
        select(RankingImportRun)
        .order_by(
            RankingImportRun.started_at.desc(),
            RankingImportRun.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
