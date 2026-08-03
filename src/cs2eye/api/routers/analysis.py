from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cs2eye.db.session import get_db_session
from cs2eye.models.demo import (
    DemoMapResult, DemoParseRun, DemoTeamOpponentContext, DemoTeamSideStat, DemoTeamRoster,
    TeamMapAggregate,
)
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team, TeamRosterMember
from cs2eye.services.team_map_aggregate_service import (
    freshness_label, recalculate_team_map, sample_size_label,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _roster_players(session: AsyncSession, roster_id: int) -> list[dict]:
    rows = (await session.execute(
        select(TeamRosterMember, Player).outerjoin(Player, Player.id == TeamRosterMember.player_id)
        .where(TeamRosterMember.roster_id == roster_id).order_by(TeamRosterMember.id)
    )).all()
    return [{"id": member.player_id, "name": player.nickname if player else member.player_name_snapshot,
             "role": member.role_snapshot} for member, player in rows]


@router.get("/compare/teams/{team_a_id}/{team_b_id}/current-rosters")
async def compare_current_rosters(
    team_a_id: int, team_b_id: int, session: AsyncSession = Depends(get_db_session),
) -> dict:
    if team_a_id == team_b_id:
        raise HTTPException(status_code=400, detail="Нужно выбрать две разные команды.")
    team_a, team_b = await session.get(Team, team_a_id), await session.get(Team, team_b_id)
    if team_a is None or team_b is None:
        raise HTTPException(status_code=404, detail="Команда не найдена.")
    if team_a.current_roster_id is None or team_b.current_roster_id is None:
        return {"status": "current_roster_unavailable", "reason": "active_roster_incomplete",
                "team_a": {"id": team_a.id, "name": team_a.name, "current_roster_id": team_a.current_roster_id, "players": []},
                "team_b": {"id": team_b.id, "name": team_b.name, "current_roster_id": team_b.current_roster_id, "players": []},
                "head_to_head": None, "maps": [], "recent_maps": []}
    link_a, link_b = aliased(DemoTeamRoster), aliased(DemoTeamRoster)
    rows = (await session.execute(
        select(DemoFile, DemoMapResult)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
        .join(link_a, (link_a.demo_file_id == DemoFile.id) & (link_a.team_id == team_a_id) &
              (link_a.roster_id == team_a.current_roster_id) & (link_a.resolution_status == "complete"))
        .join(link_b, (link_b.demo_file_id == DemoFile.id) & (link_b.team_id == team_b_id) &
              (link_b.roster_id == team_b.current_roster_id) & (link_b.resolution_status == "complete"))
        .where(DemoMapResult.round_data_status == "complete",
               or_((DemoMapResult.team_a_id == team_a_id) & (DemoMapResult.team_b_id == team_b_id),
                   (DemoMapResult.team_a_id == team_b_id) & (DemoMapResult.team_b_id == team_a_id)))
        .order_by(DemoFile.match_date.desc(), DemoFile.id.desc())
    )).all()
    recent, by_map = [], {}
    a_wins = b_wins = a_rounds = b_rounds = 0
    dates = []
    for demo, result in rows:
        a_is_side_a = result.team_a_id == team_a_id
        score_a = result.team_a_score if a_is_side_a else result.team_b_score
        score_b = result.team_b_score if a_is_side_a else result.team_a_score
        if score_a is None or score_b is None or score_a == score_b: continue
        a_wins += int(score_a > score_b); b_wins += int(score_b > score_a)
        a_rounds += score_a; b_rounds += score_b
        if demo.match_date: dates.append(demo.match_date)
        item = by_map.setdefault(result.map_name or "unknown", {"maps_played": 0, "team_a_maps_won": 0, "team_b_maps_won": 0})
        item["maps_played"] += 1; item["team_a_maps_won"] += int(score_a > score_b); item["team_b_maps_won"] += int(score_b > score_a)
        recent.append({"demo_file_id": demo.id, "match_date": demo.match_date, "tournament": demo.tournament_name,
                       "map_name": result.map_name, "team_a_score": score_a, "team_b_score": score_b,
                       "winner_team_id": team_a_id if score_a > score_b else team_b_id,
                       "went_to_overtime": bool(result.went_to_overtime)})
    return {"status": "available", "met": bool(recent),
            "team_a": {"id": team_a.id, "name": team_a.name, "current_roster_id": team_a.current_roster_id,
                       "players": await _roster_players(session, team_a.current_roster_id)},
            "team_b": {"id": team_b.id, "name": team_b.name, "current_roster_id": team_b.current_roster_id,
                       "players": await _roster_players(session, team_b.current_roster_id)},
            "head_to_head": {"maps_played": len(recent), "team_a_maps_won": a_wins, "team_b_maps_won": b_wins,
                             "team_a_rounds_won": a_rounds, "team_b_rounds_won": b_rounds,
                             "first_meeting_date": min(dates) if dates else None,
                             "last_meeting_date": max(dates) if dates else None},
            "maps": [{"map_name": name, **values} for name, values in sorted(by_map.items())],
            "recent_maps": recent[:20]}


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
            "recent": recent, "versus": versus}


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


@router.get("/teams/{team_id}/maps")
async def team_maps(team_id: int, include_inactive_maps: bool = False,
                    aggregation_level: str = Query("organization"),
                    session: AsyncSession = Depends(get_db_session)) -> dict:
    team, items = await _team_and_aggregates(session, team_id, aggregation_level)
    grouped: dict[str, list[TeamMapAggregate]] = {}
    for item in items:
        grouped.setdefault(item.map_name, []).append(item)
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


@router.get("/teams/{team_id}/maps/{map_name}")
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
