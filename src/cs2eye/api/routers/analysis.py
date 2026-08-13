from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cs2eye.db.session import get_db_session
from cs2eye.api.schemas.analysis import (
    LegacyCurrentRosterComparisonResponse, TeamH2HComparisonResponse,
    TeamMapComparisonResponse, TeamMapDetailResponse, TeamMapsResponse,
)
from cs2eye.models.demo import (
    DemoMapResult, DemoParseRun, DemoTeamOpponentContext, DemoTeamSideStat, DemoTeamRoster,
    TeamMapAggregate,
)
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team, TeamRosterMember
from cs2eye.services.team_map_aggregate_service import (
    freshness_label, recalculate_team_map, sample_size_label,
)
from cs2eye.services.team_map_strength_service import (
    MapStrengthResult, calculate_map_strength,
)
from cs2eye.services.team_h2h_service import (
    H2HTeamNotFoundError, SameTeamH2HError, TeamH2HService,
)
from cs2eye.services.veto_service import VetoError, VetoService, comparison as veto_comparison
from cs2eye.services.calculated_veto_service import CalculatedVetoService
from cs2eye.services.leadership_service import LeadershipService

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/teams/{team_id}/leadership")
async def team_leadership(team_id:int,session:AsyncSession=Depends(get_db_session))->dict:
    try:return await LeadershipService(session).team(team_id)
    except ValueError as error:raise HTTPException(404,str(error)) from error

@router.get("/teams/{team_id}/veto")
async def team_veto(team_id:int, aggregation_level:str=Query("organization",pattern="^(organization|current_roster)$"), recent:int|None=Query(None), rank_scope:str|None=Query(None), context:str|None=Query(None), session:AsyncSession=Depends(get_db_session)) -> dict:
    if recent not in (None,5,10,20): raise HTTPException(422,"recent must be 5, 10 or 20")
    try:return await VetoService(session).profile(team_id,aggregation_level=aggregation_level,recent=recent,rank_scope=rank_scope,context=context)
    except VetoError as error:raise HTTPException(404,str(error)) from error

@router.get("/compare/teams/{team_a_id}/{team_b_id}/veto")
async def compare_veto(team_a_id:int,team_b_id:int,aggregation_level:str=Query("current_roster",pattern="^(organization|current_roster)$"),session:AsyncSession=Depends(get_db_session))->dict:
    try:return await veto_comparison(session,team_a_id,team_b_id,aggregation_level)
    except VetoError as error:raise HTTPException(404,str(error)) from error

@router.get("/calculated-veto")
async def calculated_veto(team_a_id:int,team_b_id:int,format:str=Query("bo3"),first_actor:str|None=Query(None),session:AsyncSession=Depends(get_db_session))->dict:
    try:return await CalculatedVetoService(session).calculate(team_a_id,team_b_id,format,first_actor)
    except ValueError as error:raise HTTPException(422,str(error)) from error

@router.get("/calculated-veto/backtest/{match_id}")
async def calculated_veto_backtest(match_id:int,session:AsyncSession=Depends(get_db_session))->dict:
    try:return await CalculatedVetoService(session).backtest(match_id)
    except ValueError as error:raise HTTPException(422,str(error)) from error


async def _roster_players(session: AsyncSession, roster_id: int) -> list[dict]:
    rows = (await session.execute(
        select(TeamRosterMember, Player).outerjoin(Player, Player.id == TeamRosterMember.player_id)
        .where(TeamRosterMember.roster_id == roster_id).order_by(TeamRosterMember.id)
    )).all()
    return [{"id": member.player_id, "name": player.nickname if player else member.player_name_snapshot,
             "role": member.role_snapshot} for member, player in rows]


def _h2h_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SameTeamH2HError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/compare/teams/{team_a_id}/{team_b_id}/h2h",
    response_model=TeamH2HComparisonResponse,
)
async def compare_team_h2h(
    team_a_id: int,
    team_b_id: int,
    recent_limit: int = Query(default=10, ge=1, le=20),
    session: AsyncSession = Depends(get_db_session),
) -> TeamH2HComparisonResponse:
    try:
        result = await TeamH2HService(session).compare(
            team_a_id, team_b_id, recent_limit=recent_limit,
        )
    except (SameTeamH2HError, H2HTeamNotFoundError) as exc:
        raise _h2h_error(exc) from exc
    return TeamH2HComparisonResponse.model_validate(result)


@router.get(
    "/compare/teams/{team_a_id}/{team_b_id}/current-rosters",
    response_model=LegacyCurrentRosterComparisonResponse,
)
async def compare_current_rosters(
    team_a_id: int, team_b_id: int, session: AsyncSession = Depends(get_db_session),
) -> LegacyCurrentRosterComparisonResponse:
    try:
        comparison = await TeamH2HService(session).compare(team_a_id, team_b_id, recent_limit=20)
    except (SameTeamH2HError, H2HTeamNotFoundError) as exc:
        raise _h2h_error(exc) from exc
    current = comparison.current_rosters
    players_a = await _roster_players(session, comparison.team_a.current_roster_id) if comparison.team_a.current_roster_id else []
    players_b = await _roster_players(session, comparison.team_b.current_roster_id) if comparison.team_b.current_roster_id else []
    unavailable = current.status == "current_roster_unavailable"
    return LegacyCurrentRosterComparisonResponse.model_validate({
        "status": "current_roster_unavailable" if unavailable else "available",
        "reason": "active_roster_incomplete" if unavailable else None,
        "met": current.maps_played > 0,
        "team_a": {**comparison.team_a.__dict__, "players": players_a},
        "team_b": {**comparison.team_b.__dict__, "players": players_b},
        "head_to_head": None if unavailable else {
            "maps_played": current.maps_played,
            "team_a_maps_won": current.team_a.maps_won,
            "team_b_maps_won": current.team_b.maps_won,
            "team_a_rounds_won": current.team_a.rounds_won,
            "team_b_rounds_won": current.team_b.rounds_won,
            "first_meeting_date": current.first_meeting_date,
            "last_meeting_date": current.last_meeting_date,
        },
        "maps": current.maps,
        "recent_maps": current.recent_maps,
    })


class RecalculateRequest(BaseModel):
    team_id: int | None = None
    map_name: str | None = None


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _scope(item: TeamMapAggregate, today: date) -> dict:
    return {
        "maps_played": item.maps_played, "maps_won": item.maps_won,
        "maps_lost": item.maps_lost, "map_win_rate": _number(item.map_win_rate),
        "rounds_played": item.rounds_played, "rounds_won": item.rounds_won,
        "rounds_lost": item.rounds_lost, "round_win_rate": _number(item.round_win_rate),
        "ct": {"rounds_played": item.ct_rounds_played, "rounds_won": item.ct_rounds_won,
               "rounds_lost": item.ct_rounds_lost, "win_rate": _number(item.ct_win_rate)},
        "t": {"rounds_played": item.t_rounds_played, "rounds_won": item.t_rounds_won,
              "rounds_lost": item.t_rounds_lost, "win_rate": _number(item.t_win_rate)},
        "bomb": _bomb_scope(item),
        "economy": item.economy_data,
        "combat": item.combat_data,
        "utility": item.utility_data,
        "overtime_maps": item.overtime_maps,
        "overtime_rounds_played": item.overtime_rounds_played,
        "overtime_rounds_won": item.overtime_rounds_won,
        "sample_size_score": _number(item.sample_size_score),
        "sample_size_label": sample_size_label(item.maps_played),
        "freshness_score": _number(item.freshness_score),
        "freshness_label": freshness_label(item.last_match_date, today),
        "first_match_date": item.first_match_date,
        "last_match_date": item.last_match_date,
    }


def _bomb_scope(item: TeamMapAggregate) -> dict:
    return {
        "t_rounds_played": item.bomb_t_rounds_played, "plants": item.bomb_plants,
        "plant_rate": _number(item.plant_rate),
        "postplant_rounds": item.postplant_rounds, "postplant_wins": item.postplant_wins,
        "postplant_losses": item.postplant_losses, "postplant_win_rate": _number(item.postplant_win_rate),
        "retake_opportunities": item.retake_opportunities, "retake_wins": item.retake_wins,
        "retake_losses": item.retake_losses, "retake_win_rate": _number(item.retake_win_rate),
        "explosions": item.bomb_explosions, "defuses": item.bomb_defuses,
    }


def _strength_payload(result: MapStrengthResult) -> dict:
    return {
        "status": result.status,
        "map_strength_score": round(result.map_strength_score, 2) if result.map_strength_score is not None else None,
        "performance_score": round(result.performance_score, 2) if result.performance_score is not None else None,
        "confidence_score": round(result.confidence_score, 2),
        "confidence_level": result.confidence_level,
        "model_version": result.model_version, "raw_score": result.raw_score,
        "reliability": result.reliability,
        "confidence_adjustment": result.confidence_adjustment,
        "final_score": result.final_score,
        "factors": [{
            "code": factor.code, "label": factor.label,
            "score": round(factor.score, 2) if factor.score is not None else None,
            "configured_weight": factor.configured_weight,
            "effective_weight": round(factor.effective_weight, 6),
            "impact": round(factor.impact, 2),
            "explanation": factor.explanation,
            "key": factor.key, "raw_value": factor.raw_value,
            "normalized_score": factor.normalized_score, "weight": factor.weight,
            "sample_size": factor.sample_size, "confidence": factor.confidence,
            "available": factor.available, "reason": factor.reason,
            "reference_value": factor.reference_value,
            "reference_source": factor.reference_source,
        } for factor in result.factors],
        "warnings": result.warnings,
    }


def _map_payload(items: list[TeamMapAggregate], today: date) -> dict:
    indexed = {item.scope_key: item for item in items}
    all_item = indexed["all"]
    recent = {}
    for size in (5, 10, 20):
        item = indexed.get(f"recent:{size}")
        recent[f"last_{size}"] = {
            "requested_window": size, "actual_sample": item.maps_played,
            **_scope(item, today),
        } if item else None
    versus = {}
    for group in ("top_15", "top_16_30", "tier_2_3"):
        item = indexed.get(f"rank:{group}")
        versus[group] = _scope(item, today) if item else None
    return {"map_name": all_item.map_name, "all": _scope(all_item, today),
            "recent": recent, "versus": versus,
            "strength": _strength_payload(calculate_map_strength(indexed, today))}


@router.post("/team-maps/recalculate")
async def recalculate_team_maps(
    body: RecalculateRequest, session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(DemoMapResult.team_a_id, DemoMapResult.team_b_id, DemoMapResult.map_name)
    if body.map_name:
        query = query.where(DemoMapResult.map_name == body.map_name)
    rows = (await session.execute(query)).all()
    pairs = {(team_id, map_name) for a, b, map_name in rows for team_id in (a, b)
             if team_id is not None and map_name and (body.team_id is None or team_id == body.team_id)}
    stored = (await session.execute(select(TeamMapAggregate.team_id, TeamMapAggregate.map_name))).all()
    pairs.update((team_id, map_name) for team_id, map_name in stored
                 if (body.team_id is None or team_id == body.team_id)
                 and (body.map_name is None or map_name == body.map_name))
    upserted = deleted = failed = warnings = 0
    failures = []
    for team_id, map_name in sorted(pairs):
        try:
            result = await recalculate_team_map(session, team_id, map_name)
            await session.commit()
            upserted += result.aggregates_upserted
            deleted += result.aggregates_deleted
            warnings += len(result.warnings)
        except Exception as exc:
            await session.rollback()
            failed += 1
            failures.append({"team_id": team_id, "map_name": map_name, "error": str(exc)[:500]})
    return {"teams_processed": len({p[0] for p in pairs}),
            "team_map_pairs_processed": len(pairs), "aggregates_upserted": upserted,
            "aggregates_deleted": deleted, "failed_count": failed,
            "warnings_count": warnings, "failures": failures}


async def _team_and_aggregates(session: AsyncSession, team_id: int,
                               aggregation_level: str = "organization"):
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Команда не найдена.")
    if aggregation_level not in ("organization", "current_roster"):
        raise HTTPException(status_code=422, detail="aggregation_level must be organization or current_roster")
    if aggregation_level == "current_roster" and team.current_roster_id is None:
        return team, []
    level = "roster" if aggregation_level == "current_roster" else "organization"
    query = select(TeamMapAggregate).where(
        TeamMapAggregate.team_id == team_id, TeamMapAggregate.aggregation_level == level,
    )
    query = query.where(TeamMapAggregate.roster_id == team.current_roster_id) if level == "roster" else query.where(TeamMapAggregate.roster_id.is_(None))
    items = list((await session.execute(
        query.order_by(TeamMapAggregate.map_name)
    )).scalars())
    return team, items


def _group_map_aggregates(
    items: list[TeamMapAggregate],
) -> dict[str, list[TeamMapAggregate]]:
    grouped: dict[str, list[TeamMapAggregate]] = {}
    for item in items:
        grouped.setdefault(item.map_name, []).append(item)
    return grouped


def _comparison_side(items: list[TeamMapAggregate], today: date) -> dict | None:
    indexed = {item.scope_key: item for item in items}
    all_item = indexed.get("all")
    if all_item is None:
        return None
    strength = calculate_map_strength(indexed, today)
    return {
        "maps_played": all_item.maps_played,
        "maps_won": all_item.maps_won,
        "maps_lost": all_item.maps_lost,
        "map_win_rate": _number(all_item.map_win_rate),
        "map_strength_score": round(strength.map_strength_score, 2) if strength.map_strength_score is not None else None,
        "confidence_score": round(strength.confidence_score, 2),
        "confidence_level": strength.confidence_level,
        "status": strength.status,
        "bomb": _bomb_scope(all_item),
        "economy": all_item.economy_data,
        "combat": all_item.combat_data,
        "utility": all_item.utility_data,
    }


@router.get(
    "/compare/teams/{team_a_id}/{team_b_id}/maps",
    response_model=TeamMapComparisonResponse,
)
async def compare_team_maps(
    team_a_id: int,
    team_b_id: int,
    aggregation_level: str = Query("current_roster"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if team_a_id == team_b_id:
        raise HTTPException(status_code=400, detail="Нужно выбрать две разные команды.")
    if aggregation_level not in ("organization", "current_roster"):
        raise HTTPException(
            status_code=422,
            detail="aggregation_level must be organization or current_roster",
        )
    team_a, items_a = await _team_and_aggregates(session, team_a_id, aggregation_level)
    team_b, items_b = await _team_and_aggregates(session, team_b_id, aggregation_level)
    grouped_a, grouped_b = _group_map_aggregates(items_a), _group_map_aggregates(items_b)
    today = date.today()
    maps = []
    summary = {
        "team_a_advantage_maps": 0, "team_b_advantage_maps": 0,
        "close_maps": 0, "not_comparable_maps": 0,
    }
    for map_name in sorted(set(grouped_a) | set(grouped_b)):
        side_a = _comparison_side(grouped_a.get(map_name, []), today)
        side_b = _comparison_side(grouped_b.get(map_name, []), today)
        if side_a is None and side_b is None:
            comparison_status = "both_no_data"
        elif side_a is None:
            comparison_status = "team_a_no_data"
        elif side_b is None:
            comparison_status = "team_b_no_data"
        elif side_a["status"] != "available" and side_b["status"] != "available":
            comparison_status = "both_not_enough_data"
        elif side_a["status"] != "available":
            comparison_status = "team_a_not_enough_data"
        elif side_b["status"] != "available":
            comparison_status = "team_b_not_enough_data"
        else:
            comparison_status = "comparable"

        advantage_team_id = advantage_team_name = advantage_level = None
        advantage_diff = None
        if comparison_status == "comparable":
            score_a = side_a["map_strength_score"]
            score_b = side_b["map_strength_score"]
            if score_a is not None and score_b is not None:
                advantage_diff = round(abs(score_a - score_b), 2)
                if advantage_diff < 5:
                    advantage_level = "none"
                    summary["close_maps"] += 1
                else:
                    advantage_level = (
                        "small" if advantage_diff < 10 else
                        "clear" if advantage_diff < 20 else "strong"
                    )
                    if score_a > score_b:
                        advantage_team_id, advantage_team_name = team_a.id, team_a.name
                        summary["team_a_advantage_maps"] += 1
                    else:
                        advantage_team_id, advantage_team_name = team_b.id, team_b.name
                        summary["team_b_advantage_maps"] += 1
        else:
            summary["not_comparable_maps"] += 1
        maps.append({
            "map_name": map_name, "team_a": side_a, "team_b": side_b,
            "comparison_status": comparison_status,
            "advantage_team_id": advantage_team_id,
            "advantage_team_name": advantage_team_name,
            "advantage_diff": advantage_diff,
            "advantage_level": advantage_level,
        })
    maps.sort(key=lambda item: (
        item["comparison_status"] != "comparable",
        -(item["advantage_diff"] or 0) if item["comparison_status"] == "comparable" else 0,
        item["map_name"],
    ))
    roster_unavailable = (
        aggregation_level == "current_roster"
        and (team_a.current_roster_id is None or team_b.current_roster_id is None)
    )
    return {
        "aggregation_level": aggregation_level,
        "team_a": {"id": team_a.id, "name": team_a.name, "rank": team_a.current_rank,
                   "roster_id": team_a.current_roster_id if aggregation_level == "current_roster" else None},
        "team_b": {"id": team_b.id, "name": team_b.name, "rank": team_b.current_rank,
                   "roster_id": team_b.current_roster_id if aggregation_level == "current_roster" else None},
        "status": "current_roster_unavailable" if roster_unavailable else "available",
        "maps": maps, "summary": summary,
    }


@router.get("/teams/{team_id}/maps", response_model=TeamMapsResponse)
async def team_maps(team_id: int, include_inactive_maps: bool = False,
                    aggregation_level: str = Query("organization"),
                    session: AsyncSession = Depends(get_db_session)) -> dict:
    team, items = await _team_and_aggregates(session, team_id, aggregation_level)
    grouped = _group_map_aggregates(items)
    maps = [_map_payload(group, date.today()) for group in grouped.values()
            if any(item.scope_key == "all" for item in group)]
    maps.sort(key=lambda item: item["all"]["maps_played"], reverse=True)
    all_items = [item for item in items if item.scope_key == "all"]
    return {"team": {"id": team.id, "name": team.name, "rank": team.current_rank},
            "aggregation_level": aggregation_level,
            "roster_id": team.current_roster_id if aggregation_level == "current_roster" else None,
            "status": "current_roster_unavailable" if aggregation_level == "current_roster" and team.current_roster_id is None else "available",
            "roster_sample": {"maps_played": sum(x.maps_played for x in all_items),
                              "first_match_date": min((x.first_match_date for x in all_items if x.first_match_date), default=None),
                              "last_match_date": max((x.last_match_date for x in all_items if x.last_match_date), default=None)} if aggregation_level == "current_roster" else None,
            "maps": maps}


@router.get("/teams/{team_id}/maps/{map_name}", response_model=TeamMapDetailResponse)
async def team_map_detail(team_id: int, map_name: str,
                          aggregation_level: str = Query("organization"),
                          session: AsyncSession = Depends(get_db_session)) -> dict:
    team, items = await _team_and_aggregates(session, team_id, aggregation_level)
    selected = [item for item in items if item.map_name == map_name]
    if not any(item.scope_key == "all" for item in selected):
        if aggregation_level == "current_roster":
            return {"team": {"id": team.id, "name": team.name, "rank": team.current_rank},
                    "aggregation_level": aggregation_level, "roster_id": team.current_roster_id,
                    "status": "current_roster_not_available" if team.current_roster_id is None else "no_maps_for_current_roster",
                    "map_name": map_name, "recent_matches": []}
        raise HTTPException(status_code=404, detail="По этой карте нет агрегированных данных.")
    query = (
        select(DemoFile, DemoMapResult, DemoTeamSideStat, DemoTeamOpponentContext)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
        .join(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id)
        .join(DemoTeamSideStat, (DemoTeamSideStat.demo_file_id == DemoFile.id) &
              (DemoTeamSideStat.team_id == team_id))
        .outerjoin(DemoTeamOpponentContext,
              (DemoTeamOpponentContext.demo_file_id == DemoFile.id) &
              (DemoTeamOpponentContext.team_id == team_id))
        .where(DemoParseRun.status == "success",
               DemoMapResult.metadata_status.in_(("complete", "needs_review")),
               DemoMapResult.round_data_status == "complete",
               DemoMapResult.team_a_score.is_not(None),
               DemoMapResult.team_b_score.is_not(None),
               DemoMapResult.map_name == map_name,
               or_(DemoMapResult.team_a_id == team_id, DemoMapResult.team_b_id == team_id))
        .order_by(DemoFile.match_date.desc(), DemoFile.id.desc()).limit(20)
    )
    if aggregation_level == "current_roster":
        query = query.join(DemoTeamRoster, (DemoTeamRoster.demo_file_id == DemoFile.id) &
                           (DemoTeamRoster.team_id == team_id) &
                           (DemoTeamRoster.roster_id == team.current_roster_id) &
                           (DemoTeamRoster.resolution_status == "complete"))
    rows = (await session.execute(query)).all()
    recent_matches = []
    for demo, result, side, context in rows:
        is_a = result.team_a_id == team_id
        score_for = result.team_a_score if is_a else result.team_b_score
        score_against = result.team_b_score if is_a else result.team_a_score
        if (score_for is None or score_against is None or score_for == score_against
                or side.total_rounds_played != score_for + score_against
                or side.total_rounds_won != score_for
                or side.total_rounds_lost != score_against):
            continue
        recent_matches.append({
            "demo_file_id": demo.id, "match_date": demo.match_date,
            "opponent_team_id": context.opponent_team_id if context else (result.team_b_id if is_a else result.team_a_id),
            "opponent_team_name": context.opponent_team_name if context else (result.team_b_name if is_a else result.team_a_name),
            "opponent_rank": context.opponent_rank if context else None,
            "opponent_rank_group": (
                "tier_2_3" if context and context.opponent_team_id is None
                and context.opponent_team_name else
                (context.opponent_rank_group if context else "unknown")
            ),
            "score_for": score_for, "score_against": score_against,
            "result": "win" if score_for > score_against else "loss",
            "ct_rounds_won": side.ct_rounds_won, "ct_rounds_played": side.ct_rounds_played,
            "t_rounds_won": side.t_rounds_won, "t_rounds_played": side.t_rounds_played,
        })
    return {"team": {"id": team.id, "name": team.name, "rank": team.current_rank},
            "aggregation_level": aggregation_level,
            "roster_id": team.current_roster_id if aggregation_level == "current_roster" else None,
            **_map_payload(selected, date.today()), "recent_matches": recent_matches}
