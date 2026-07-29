import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import DemoParseFileResult, DemoParseResponse
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.demo_parser_service import Demoparser2Adapter
from cs2eye.services.demo_player_link_service import link_demo_player
from cs2eye.services.player_internal_rating_service import recalculate_players_internal_rating
from cs2eye.services.demo_storage_service import make_tournament_slug
from cs2eye.services.demo_team_link_service import resolve_demo_opponents


class DemoParseService:
    def __init__(self, session: AsyncSession, storage_root: str | Path) -> None:
        self.session = session
        self.storage_root = Path(storage_root)
        self.parser = Demoparser2Adapter()

    async def parse_many(
        self, tournament_name: str, year: int, replace_existing: bool,
    ) -> DemoParseResponse:
        slug = make_tournament_slug(tournament_name)
        demos = (
            await self.session.execute(select(DemoFile).where(
                DemoFile.tournament_slug == slug,
                extract("year", DemoFile.match_date) == year,
            ).order_by(DemoFile.match_date, DemoFile.original_filename))
        ).scalars().all()
        results: list[DemoParseFileResult] = []
        affected: set[int] = set()
        for demo in demos:
            result, player_ids = await self.parse_one(demo, replace_existing)
            results.append(result)
            affected.update(player_ids)
        recalculated = await recalculate_players_internal_rating(self.session, affected)
        return DemoParseResponse(
            tournament_name=tournament_name, year=year, total_files=len(demos),
            parsed_count=sum(item.status == "parsed" for item in results),
            skipped_count=sum(item.status == "skipped" for item in results),
            failed_count=sum(item.status == "failed" for item in results),
            players_recalculated=recalculated, files=results,
        )

    async def parse_by_id(
        self, demo_file_id: int, replace_existing: bool,
    ) -> tuple[DemoParseFileResult, set[int]] | None:
        demo = await self.session.get(DemoFile, demo_file_id)
        if demo is None:
            return None
        result, affected = await self.parse_one(demo, replace_existing)
        await recalculate_players_internal_rating(self.session, affected)
        return result, affected

    async def parse_one(
        self, demo: DemoFile, replace_existing: bool,
    ) -> tuple[DemoParseFileResult, set[int]]:
        run = (
            await self.session.execute(select(DemoParseRun).where(
                DemoParseRun.demo_file_id == demo.id,
            ))
        ).scalar_one_or_none()
        if run and run.status == "success" and not replace_existing:
            return DemoParseFileResult(
                demo_file_id=demo.id, filename=demo.original_filename,
                status="skipped",
            ), set()
        previous_success = bool(run and run.status == "success")
        if run is None:
            run = DemoParseRun(
                demo_file_id=demo.id, status="processing",
                parser_name=self.parser.parser_name,
                parser_version=self.parser.parser_version,
            )
            self.session.add(run)
        run.status = "processing"
        run.parser_name = self.parser.parser_name
        run.parser_version = self.parser.parser_version
        run.started_at = datetime.now(UTC)
        run.finished_at = None
        run.error_message = None
        await self.session.commit()
        try:
            parsed = await asyncio.to_thread(
                self.parser.parse, self.storage_root / demo.storage_path,
            )
            if not parsed:
                raise ValueError("No valid player statistics were found in the demo.")
            opponent_snapshots, diagnostics = await resolve_demo_opponents(
                self.session, parsed,
            )
            old_ids = set((
                await self.session.execute(select(DemoPlayerStat.player_id).where(
                    DemoPlayerStat.demo_file_id == demo.id,
                    DemoPlayerStat.player_id.is_not(None),
                ))
            ).scalars().all())
            await self.session.execute(delete(DemoPlayerStat).where(
                DemoPlayerStat.demo_file_id == demo.id,
            ))
            linked_ids: set[int] = set()
            unlinked_players: list[dict[str, str | None]] = []
            for item in parsed:
                opponent = opponent_snapshots[item.identity_key]
                player = await link_demo_player(
                    self.session, item.steam_id, item.nickname,
                )
                if player is not None:
                    linked_ids.add(player.id)
                else:
                    unlinked_players.append({
                        "nickname": item.nickname, "steam_id": item.steam_id,
                        "team_name": item.team_name,
                        "demo_filename": demo.original_filename,
                    })
                self.session.add(DemoPlayerStat(
                    demo_file_id=demo.id, parse_run_id=run.id,
                    player_id=player.id if player else None,
                    steam_id=item.steam_id, identity_key=item.identity_key,
                    nickname=item.nickname, team_name=item.team_name,
                    rounds_played=item.rounds_played, kills=item.kills,
                    deaths=item.deaths, assists=item.assists,
                    total_damage=item.total_damage, adr=item.adr,
                    kast_rounds=item.kast_rounds, kast_percent=item.kast_percent,
                    internal_rating=item.internal_rating,
                    internal_rating_version=item.internal_rating_version,
                    demo_team_id=opponent.demo_team_id,
                    demo_team_name=opponent.demo_team_name,
                    opponent_team_id=opponent.opponent_team_id,
                    opponent_team_name=opponent.opponent_team_name,
                    opponent_rank=opponent.opponent_rank,
                    opponent_rank_group=opponent.opponent_rank_group,
                ))
            run.status = "success"
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
            return DemoParseFileResult(
                demo_file_id=demo.id, filename=demo.original_filename,
                status="parsed", players_found=len(parsed),
                players_linked=len(linked_ids),
                players_unlinked=len(parsed) - len(linked_ids),
                unlinked_players=unlinked_players,
                diagnostics=diagnostics,
            ), old_ids | linked_ids
        except Exception as error:
            await self.session.rollback()
            run = (
                await self.session.execute(select(DemoParseRun).where(
                    DemoParseRun.demo_file_id == demo.id,
                ))
            ).scalar_one()
            run.status = "success" if previous_success else "failed"
            run.finished_at = datetime.now(UTC)
            run.error_message = str(error)[:2000]
            await self.session.commit()
            return DemoParseFileResult(
                demo_file_id=demo.id, filename=demo.original_filename,
                status="failed", error=str(error),
            ), set()
