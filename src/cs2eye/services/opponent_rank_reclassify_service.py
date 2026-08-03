from dataclasses import dataclass

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import DemoRankReclassifyResponse
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.demo_storage_service import make_tournament_slug
from cs2eye.services.opponent_rank_resolver import (
    ResolvedOpponentRank,
    resolve_opponent_rank,
)
from cs2eye.services.player_internal_rating_service import (
    recalculate_players_internal_rating,
)
from cs2eye.services.demo_opponent_context_service import rebuild_demo_opponent_contexts_from_player_stats
from cs2eye.services.team_map_aggregate_service import recalculate_demo_affected_aggregates


@dataclass(frozen=True)
class DemoReclassifyCounts:
    checked: int
    updated: int
    unchanged: int
    player_ids: set[int]


class OpponentRankReclassifyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reclassify_one(
        self,
        demo_file_id: int,
        *,
        only_unknown_or_fallback: bool = False,
    ) -> DemoRankReclassifyResponse | None:
        demo = await self._load_successful_demo(demo_file_id)
        if demo is None:
            return None
        try:
            counts = await self._reclassify_demo(
                demo, only_unknown_or_fallback=only_unknown_or_fallback,
            )
            await self.session.commit()
            recalculated = await recalculate_players_internal_rating(
                self.session, counts.player_ids,
            )
            return DemoRankReclassifyResponse(
                demo_files_found=1,
                player_stats_checked=counts.checked,
                updated_count=counts.updated,
                unchanged_count=counts.unchanged,
                failed_count=0,
                players_recalculated=recalculated,
            )
        except Exception:
            await self.session.rollback()
            raise

    async def reclassify_many(
        self,
        tournament_name: str,
        year: int,
        *,
        only_unknown_or_fallback: bool,
    ) -> DemoRankReclassifyResponse:
        demos = list((await self.session.execute(
            select(DemoFile)
            .join(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id)
            .where(
                DemoFile.tournament_slug == make_tournament_slug(tournament_name),
                extract("year", DemoFile.match_date) == year,
                DemoParseRun.status == "success",
            )
            .order_by(DemoFile.match_date, DemoFile.id)
        )).scalars())
        checked = updated = unchanged = failed = 0
        player_ids: set[int] = set()
        failures: list[dict[str, str | int]] = []
        for demo in demos:
            try:
                counts = await self._reclassify_demo(
                    demo, only_unknown_or_fallback=only_unknown_or_fallback,
                )
                await self.session.commit()
                checked += counts.checked
                updated += counts.updated
                unchanged += counts.unchanged
                player_ids.update(counts.player_ids)
            except Exception as exc:
                await self.session.rollback()
                failed += 1
                failures.append({
                    "demo_file_id": demo.id,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })
        recalculated = await recalculate_players_internal_rating(
            self.session, player_ids,
        )
        return DemoRankReclassifyResponse(
            demo_files_found=len(demos),
            player_stats_checked=checked,
            updated_count=updated,
            unchanged_count=unchanged,
            failed_count=failed,
            players_recalculated=recalculated,
            failures=failures,
        )

    async def _load_successful_demo(self, demo_file_id: int) -> DemoFile | None:
        return (await self.session.execute(
            select(DemoFile)
            .join(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id)
            .where(
                DemoFile.id == demo_file_id,
                DemoParseRun.status == "success",
            )
        )).scalar_one_or_none()

    async def _reclassify_demo(
        self,
        demo: DemoFile,
        *,
        only_unknown_or_fallback: bool,
    ) -> DemoReclassifyCounts:
        query = select(DemoPlayerStat).where(
            DemoPlayerStat.demo_file_id == demo.id,
        )
        if only_unknown_or_fallback:
            query = query.where(
                DemoPlayerStat.opponent_rank_source.in_((
                    "current_fallback", "unknown",
                )),
            )
        stats = list((await self.session.execute(query)).scalars())
        resolved_by_team: dict[int | None, ResolvedOpponentRank] = {}
        for team_id in {item.opponent_team_id for item in stats}:
            resolved_by_team[team_id] = await resolve_opponent_rank(
                self.session, team_id, demo.match_date,
            )

        updated = 0
        player_ids: set[int] = set()
        for item in stats:
            resolved = resolved_by_team[item.opponent_team_id]
            before = (
                item.opponent_rank,
                item.opponent_rank_group,
                item.opponent_rank_source,
                item.opponent_rank_snapshot_id,
                item.opponent_rank_snapshot_date,
            )
            after = (
                resolved.rank,
                resolved.rank_group,
                resolved.source,
                resolved.snapshot_id,
                resolved.snapshot_date,
            )
            if before == after:
                continue
            (
                item.opponent_rank,
                item.opponent_rank_group,
                item.opponent_rank_source,
                item.opponent_rank_snapshot_id,
                item.opponent_rank_snapshot_date,
            ) = after
            updated += 1
            if item.player_id is not None:
                player_ids.add(item.player_id)
        await self.session.flush()
        await rebuild_demo_opponent_contexts_from_player_stats(self.session, demo.id)
        await self.session.flush()
        await recalculate_demo_affected_aggregates(self.session, demo.id)
        return DemoReclassifyCounts(
            checked=len(stats),
            updated=updated,
            unchanged=len(stats) - updated,
            player_ids=player_ids,
        )
