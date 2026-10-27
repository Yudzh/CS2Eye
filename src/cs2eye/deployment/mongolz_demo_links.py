"""Recover parsed maps left unlinked before the TheMongolz alias existed."""
from dataclasses import asdict
from types import SimpleNamespace

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, MatchVetoAction, Tournament
from cs2eye.services.demo_map_result_service import ParsedMapResult, apply_to_model, normalize_parsed_map_result
from cs2eye.services.demo_opponent_context_service import replace_demo_opponent_contexts
from cs2eye.services.demo_team_link_service import resolve_demo_opponents
from cs2eye.services.demo_team_resolver import normalize_team_name
from cs2eye.services.match_service import MatchService
from cs2eye.services.team_roster_service import resolve_demo_rosters
from cs2eye.services.team_map_aggregate_service import recalculate_demo_affected_aggregates


async def apply(session: AsyncSession) -> list[int]:
    rows = (await session.execute(select(DemoFile, DemoMapResult).join(
        DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id,
    ).join(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id).where(
        DemoFile.match_id.is_(None), DemoParseRun.status == "success",
        DemoMapResult.round_data_status == "complete",
        or_(DemoMapResult.team_a_id.is_(None), DemoMapResult.team_b_id.is_(None)),
    ))).all()
    repaired = []
    for demo, result in rows:
        if not any(normalize_team_name(name) == "the mongolz" for name in (result.team_a_name, result.team_b_name)):
            continue
        normalized = await normalize_parsed_map_result(session, ParsedMapResult(
            raw_map_name=result.map_name, team_a_name=result.team_a_name,
            team_b_name=result.team_b_name, team_a_score=result.team_a_score,
            team_b_score=result.team_b_score, parser_rounds_count=result.rounds_count,
        ))
        if normalized.metadata_status != "complete":
            raise ValueError(f"Mongolz demo {demo.original_filename}: incomplete metadata after alias repair")
        a, b = normalized.team_a.team_id, normalized.team_b.team_id
        targets = list((await session.scalars(select(Match).join(Tournament).where(
            Tournament.name == demo.tournament_name, Tournament.year == demo.match_date.year,
            Match.match_date == demo.match_date,
            or_((Match.team_a_id == a) & (Match.team_b_id == b),
                (Match.team_a_id == b) & (Match.team_b_id == a)),
        ))).all())
        if len(targets) != 1:
            raise ValueError(f"Mongolz demo {demo.original_filename}: expected one existing series, found {len(targets)}")
        target = targets[0]
        number = MatchService._filename_map_number(demo.original_filename)
        if number is None:
            raise ValueError(f"Mongolz demo {demo.original_filename}: missing map number")
        occupied = await session.scalar(select(DemoFile.id).where(
            DemoFile.match_id == target.id, DemoFile.map_number == number,
        ))
        if occupied is not None:
            raise ValueError(f"Mongolz demo {demo.original_filename}: map slot already occupied")
        apply_to_model(result, normalized, result.result_source)
        demo.match_id, demo.map_number = target.id, number
        selection = await session.scalar(select(MatchVetoAction).where(
            MatchVetoAction.match_series_id == target.id,
            MatchVetoAction.map_name == result.map_name,
            MatchVetoAction.action.in_(("pick", "decider")),
        ))
        if selection is not None:
            demo.picked_by_team_id = selection.team_id
            demo.map_role = "decider" if selection.action == "decider" else "team_pick"
        stats = list((await session.scalars(select(DemoPlayerStat).where(DemoPlayerStat.demo_file_id == demo.id))).all())
        if stats:
            snapshots, diagnostics = await resolve_demo_opponents(session, [SimpleNamespace(
                identity_key=p.identity_key, team_name=p.demo_team_name or p.team_name,
            ) for p in stats], demo.match_date)
            if any(s.demo_team_id is None or s.opponent_team_id is None for s in snapshots.values()):
                raise ValueError(f"Mongolz demo {demo.original_filename}: unresolved player teams: {diagnostics}")
            for player in stats:
                for key, value in asdict(snapshots[player.identity_key]).items():
                    setattr(player, key, value)
            await replace_demo_opponent_contexts(session, demo.id, snapshots.values())
            await session.flush()
            await resolve_demo_rosters(session, demo.id, replace_existing=True)
        await session.flush()
        await recalculate_demo_affected_aggregates(session, demo.id)
        repaired.append(demo.id)
    return repaired
