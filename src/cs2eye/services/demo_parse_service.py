import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import delete, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import DemoParseFileResult, DemoParseResponse
from cs2eye.models.demo import DemoMapResult, DemoParseRun, DemoPlayerStat, DemoTeamSideStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.demo_parser_service import Demoparser2Adapter, ParsedDemoPlayerStat
from cs2eye.services.demo_player_link_service import link_demo_player
from cs2eye.services.player_internal_rating_service import (
    calculate_internal_rating, recalculate_players_internal_rating,
)
from cs2eye.services.demo_storage_service import make_tournament_slug
from cs2eye.services.demo_team_link_service import resolve_demo_opponents
from cs2eye.services.demo_opponent_context_service import replace_demo_opponent_contexts
from cs2eye.services.demo_map_result_service import ParsedMapResult, apply_to_model, normalize_parsed_map_result
from cs2eye.services.demo_parser_service import ParsedDemo
from cs2eye.services.demo_round_service import (
    normalize_rounds, recalculate_demo_team_side_stats, replace_rounds,
    round_data_status, stitch_split_rounds,
)
from cs2eye.services.team_map_aggregate_service import recalculate_demo_affected_aggregates
from cs2eye.services.team_roster_service import resolve_demo_rosters
from cs2eye.services.match_service import MatchService, MatchValidationError

logger = logging.getLogger(__name__)


def _part_number(filename: str) -> tuple[str, int] | None:
    match = re.match(r"^(.*)-p([1-9])\.dem$", filename, re.IGNORECASE)
    return (match.group(1), int(match.group(2))) if match else None


def merge_player_stats(parts: list[list[ParsedDemoPlayerStat]]) -> list[ParsedDemoPlayerStat]:
    grouped: dict[str, list[ParsedDemoPlayerStat]] = {}
    for stats in parts:
        for item in stats:
            grouped.setdefault(item.identity_key, []).append(item)
    merged = []
    for items in grouped.values():
        rounds = sum(item.rounds_played for item in items)
        kills = sum(item.kills for item in items)
        deaths = sum(item.deaths for item in items)
        assists = sum(item.assists for item in items)
        damage = sum(item.total_damage for item in items)
        kast_rounds = sum(item.kast_rounds for item in items)
        adr = (Decimal(damage) / Decimal(rounds)).quantize(Decimal("0.0001"))
        kast = (Decimal(kast_rounds) * 100 / Decimal(rounds)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP,
        )
        first = items[0]
        merged.append(ParsedDemoPlayerStat(
            steam_id=first.steam_id, nickname=first.nickname,
            team_name=next((item.team_name for item in reversed(items) if item.team_name), None),
            rounds_played=rounds, kills=kills, deaths=deaths, assists=assists,
            total_damage=damage, adr=adr, kast_rounds=kast_rounds,
            kast_percent=kast,
            internal_rating=calculate_internal_rating(
                rounds_played=rounds, kills=kills, deaths=deaths,
                assists=assists, adr=adr, kast_percent=kast,
            ),
        ))
    return sorted(merged, key=lambda item: item.nickname.casefold())


class DemoParseService:
    def __init__(self, session: AsyncSession, storage_root: str | Path) -> None:
        self.session = session
        self.storage_root = Path(storage_root)
        self.parser = Demoparser2Adapter()

    async def parse_many(
        self, tournament_name: str, year: int, replace_existing: bool,
        progress_callback: Callable[[int, int, DemoParseFileResult | None], Awaitable[None]] | None = None,
    ) -> DemoParseResponse:
        slug = make_tournament_slug(tournament_name)
        demos = (
            await self.session.execute(select(DemoFile).where(
                DemoFile.tournament_slug == slug,
                extract("year", DemoFile.match_date) == year,
            ).order_by(DemoFile.match_date, DemoFile.original_filename))
        ).scalars().all()
        return await self._parse_demos(
            demos, replace_existing,
            tournament_name=tournament_name, year=year,
            progress_callback=progress_callback,
        )

    async def parse_all(
        self,
        replace_existing: bool = True,
        progress_callback: Callable[[int, int, DemoParseFileResult | None], Awaitable[None]] | None = None,
    ) -> DemoParseResponse:
        demos = (
            await self.session.execute(
                select(DemoFile).order_by(
                    DemoFile.match_date, DemoFile.original_filename,
                )
            )
        ).scalars().all()
        missing = [
            demo for demo in demos
            if not (self.storage_root / demo.storage_path).is_file()
        ]
        if missing:
            examples = ", ".join(
                f"#{demo.id} {demo.storage_path}" for demo in missing[:3]
            )
            raise FileNotFoundError(
                f"Хранилище демок недоступно: не найдено файлов {len(missing)} "
                f"из {len(demos)}. Примеры: {examples}. "
                "Проверьте volume /app/storage и сохранённые storage_path. "
                "Массовый парсинг не запущен, существующие результаты сохранены."
            )
        return await self._parse_demos(
            demos, replace_existing,
            tournament_name="Все турниры", year=0,
            progress_callback=progress_callback,
        )

    async def _parse_demos(
        self,
        demos: list[DemoFile],
        replace_existing: bool,
        *,
        tournament_name: str,
        year: int,
        progress_callback: Callable[[int, int, DemoParseFileResult | None], Awaitable[None]] | None = None,
    ) -> DemoParseResponse:
        results: list[DemoParseFileResult] = []
        affected: set[int] = set()
        if progress_callback is not None:
            await progress_callback(0, len(demos), None)
        for demo in demos:
            result, player_ids = await self.parse_one(demo, replace_existing)
            results.append(result)
            affected.update(player_ids)
            if progress_callback is not None:
                await progress_callback(len(results), len(demos), result)
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
            parsed_demo = await asyncio.to_thread(
                self.parser.parse, self.storage_root / demo.storage_path,
            )
            merged_previous_parts: list[DemoFile] = []
            part = _part_number(demo.original_filename)
            is_final_part = True
            if part:
                siblings = list((await self.session.execute(select(DemoFile).where(
                    DemoFile.tournament_slug == demo.tournament_slug,
                    DemoFile.match_date == demo.match_date,
                ))).scalars().all())
                split_parts = sorted(
                    (candidate_part[1], candidate)
                    for candidate in siblings
                    if (candidate_part := _part_number(candidate.original_filename))
                    and candidate_part[0] == part[0]
                )
                is_final_part = bool(split_parts) and part[1] == split_parts[-1][0]
                if is_final_part and part[1] > 1:
                    merged_previous_parts = [candidate for number, candidate in split_parts if number < part[1]]
                    previous = [
                        await asyncio.to_thread(self.parser.parse, self.storage_root / candidate.storage_path)
                        for candidate in merged_previous_parts
                    ]
                    parsed_demo = ParsedDemo(
                        map_result=parsed_demo.map_result,
                        player_stats=merge_player_stats([*[item.player_stats for item in previous], parsed_demo.player_stats]),
                        rounds=stitch_split_rounds(
                            [item.rounds for item in [*previous, parsed_demo]],
                            parsed_demo.map_result.team_a_name,
                            parsed_demo.map_result.team_b_name,
                        ),
                    )
            # Keep third-party/test adapters using the pre-iteration list contract
            # operational; their map result is intentionally partial, never guessed.
            if isinstance(parsed_demo, list):
                names = list(dict.fromkeys(item.team_name for item in parsed_demo if item.team_name))
                parsed_demo = ParsedDemo(
                    ParsedMapResult(
                        team_a_name=names[0] if names else None,
                        team_b_name=names[1] if len(names) > 1 else None,
                    ),
                    parsed_demo,
                )
            parsed = parsed_demo.player_stats
            if not parsed:
                raise ValueError("No valid player statistics were found in the demo.")
            normalized_result = await normalize_parsed_map_result(
                self.session, parsed_demo.map_result,
                completed_map=not part or is_final_part,
            )
            logger.info(
                "demo_map_metadata demo_file_id=%s raw_map=%r map=%r raw_teams=%r resolved_team_ids=%r raw_score=%r winner=%r rounds=%r overtime=%r issues=%r",
                demo.id, parsed_demo.map_result.raw_map_name, normalized_result.map_name,
                [parsed_demo.map_result.team_a_name, parsed_demo.map_result.team_b_name],
                [normalized_result.team_a.team_id, normalized_result.team_b.team_id],
                [parsed_demo.map_result.team_a_score, parsed_demo.map_result.team_b_score],
                normalized_result.winner_team_name, normalized_result.rounds_count,
                normalized_result.went_to_overtime,
                [issue.code for issue in normalized_result.issues],
            )
            opponent_snapshots, diagnostics = await resolve_demo_opponents(
                self.session, parsed, demo.match_date,
            )
            diagnostics.extend(await replace_demo_opponent_contexts(
                self.session, demo.id, opponent_snapshots.values(),
            ))
            old_ids = set((
                await self.session.execute(select(DemoPlayerStat.player_id).where(
                    DemoPlayerStat.demo_file_id == demo.id,
                    DemoPlayerStat.player_id.is_not(None),
                ))
            ).scalars().all())
            for previous_part in merged_previous_parts:
                old_ids.update((await self.session.execute(select(DemoPlayerStat.player_id).where(
                    DemoPlayerStat.demo_file_id == previous_part.id,
                    DemoPlayerStat.player_id.is_not(None),
                ))).scalars().all())
                await self.session.execute(delete(DemoPlayerStat).where(DemoPlayerStat.demo_file_id == previous_part.id))
                previous_result = (await self.session.execute(select(DemoMapResult).where(
                    DemoMapResult.demo_file_id == previous_part.id,
                ))).scalar_one_or_none()
                if previous_result is not None:
                    previous_result.metadata_status = "partial"
                    previous_result.round_data_status = "partial"
                await self.session.execute(delete(DemoTeamSideStat).where(DemoTeamSideStat.demo_file_id == previous_part.id))
            await self.session.execute(delete(DemoPlayerStat).where(
                DemoPlayerStat.demo_file_id == demo.id,
            ))
            map_result = (
                await self.session.execute(select(DemoMapResult).where(
                    DemoMapResult.demo_file_id == demo.id,
                ))
            ).scalar_one_or_none()
            if map_result is None:
                map_result = DemoMapResult(
                    demo_file_id=demo.id, result_source="demo_parser",
                    metadata_status="partial",
                )
                self.session.add(map_result)
            apply_to_model(map_result, normalized_result, "demo_parser")
            diagnostics.extend(issue.code for issue in normalized_result.issues)
            await self.session.flush()
            normalized_rounds, round_warnings = normalize_rounds(parsed_demo.rounds, map_result)
            status, consistency_warnings = round_data_status(normalized_rounds, map_result)
            await replace_rounds(self.session, map_result, normalized_rounds)
            await self.session.flush()
            await recalculate_demo_team_side_stats(self.session, map_result)
            map_result.round_data_status = status
            blocking_round_issues = {
                "unknown_round_side", "unknown_round_winner",
                "round_score_mismatch", "invalid_score_transition",
            }
            map_result.rounds_parsed_count = sum(
                item.is_complete and not blocking_round_issues.intersection(item.issues)
                for item in normalized_rounds
            )
            diagnostics.extend(round_warnings)
            diagnostics.extend(consistency_warnings)
            diagnostics = list(dict.fromkeys(diagnostics))
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
                    opponent_rank_source=opponent.opponent_rank_source,
                    opponent_rank_snapshot_id=opponent.opponent_rank_snapshot_id,
                    opponent_rank_snapshot_date=opponent.opponent_rank_snapshot_date,
                ))
            run.status = "success"
            run.finished_at = datetime.now(UTC)
            await self.session.flush()
            await resolve_demo_rosters(self.session, demo.id, replace_existing=replace_existing)
            await recalculate_demo_affected_aggregates(self.session, demo.id)
            # A series cannot be identified until both organizations are linked.
            # The team resolver already emits the actionable unknown-team warning;
            # avoid adding a redundant generic series warning in that case.
            if map_result.team_a_id is not None and map_result.team_b_id is not None:
                try:
                    await MatchService(self.session).auto_group_demo(demo.id)
                except MatchValidationError:
                    diagnostics.append("match_series_unresolved")
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
