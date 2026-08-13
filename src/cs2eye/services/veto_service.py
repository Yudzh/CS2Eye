from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import exp
import re

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoTeamOpponentContext, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry, Match, MatchVetoAction
from cs2eye.models.team import Team
from cs2eye.services.demo_team_resolver import team_name_aliases

VALID_MAPS = {"ancient", "anubis", "cache", "cobblestone", "dust2", "inferno", "mirage", "nuke", "overpass", "train", "vertigo"}

class VetoError(ValueError): pass

def parse_veto_text(match: Match, team_a: Team | None, team_b: Team | None, text: str) -> list[dict]:
    """Parse common human-readable veto lines without guessing unknown teams/actions."""
    teams = [team for team in (team_a, team_b) if team is not None]
    by_name = {
        alias: team
        for team in teams
        for alias in team_name_aliases(team.name)
    }
    actions: list[dict] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\s*\d+\s*[.)]\s*", "", line).strip()
        leftover = re.fullmatch(r"(.+?)\s+(?:was\s+)?left\s+over[.!]?", line, re.IGNORECASE)
        if leftover:
            actions.append({"order_index": len(actions) + 1, "team_id": None,
                            "team_name": None, "action": "decider",
                            "map_name": normalize_map(leftover.group(1))})
            continue
        acted = re.fullmatch(r"(.+?)\s+(removed|banned|picked)\s+(.+?)[.!]?", line, re.IGNORECASE)
        if not acted:
            raise VetoError(f"Строка {line_number}: ожидается 'Team removed Map', 'Team picked Map' или 'Map was left over'.")
        team_name, verb, map_name = acted.groups()
        matched = {
            by_name[alias].id: by_name[alias]
            for alias in team_name_aliases(team_name)
            if alias in by_name
        }
        team = next(iter(matched.values())) if len(matched) == 1 else None
        if team is None:
            expected = " / ".join(team.name for team in teams) or "команды серии"
            raise VetoError(f"Строка {line_number}: команда '{team_name}' не участвует в серии; ожидается {expected}.")
        actions.append({"order_index": len(actions) + 1, "team_id": team.id,
                        "team_name": team.name,
                        "action": "pick" if verb.casefold() == "picked" else "ban",
                        "map_name": normalize_map(map_name)})
    if not actions:
        raise VetoError("Введите хотя бы одно действие veto.")
    return actions

def rate(count: int, denominator: int) -> float | None:
    return count / denominator * 100 if denominator else None

def normalize_map(value: str) -> str:
    return value.strip().lower().removeprefix("de_")

def validate_actions(match: Match, actions: list[dict], pool_maps: set[str] | None = None) -> tuple[str, list[str]]:
    issues: list[str] = []
    orders = [a["order_index"] for a in actions]
    if len(orders) != len(set(orders)) or orders != sorted(orders): issues.append("duplicate_or_unsorted_order")
    seen: dict[str, str] = {}; deciders = 0
    for pos, item in enumerate(actions):
        action, map_name = item["action"], normalize_map(item["map_name"])
        if action not in {"ban", "pick", "decider"}: issues.append("unknown_action")
        if map_name not in VALID_MAPS: issues.append(f"unknown_map:{map_name}")
        elif pool_maps is not None and map_name not in pool_maps: issues.append(f"map_outside_pool:{map_name}")
        if map_name in seen: issues.append(f"duplicate_map:{map_name}")
        seen[map_name] = action
        if action == "decider":
            deciders += 1
            if pos != len(actions) - 1: issues.append("action_after_decider")
        if action != "decider" and item.get("team_id") not in {match.team_a_id, match.team_b_id}: issues.append("unknown_team")
        if action == "decider" and item.get("team_id") is not None: issues.append("decider_has_team")
    if deciders > 1: issues.append("multiple_deciders")
    hard = any(x in issues for x in ("duplicate_or_unsorted_order", "unknown_action", "unknown_team", "multiple_deciders", "action_after_decider")) or any(x.startswith("duplicate_map") for x in issues)
    return ("invalid" if hard else "needs_review" if issues else "complete"), issues

class VetoService:
    def __init__(self, session: AsyncSession): self.session = session

    async def actions(self, match_id: int) -> list[MatchVetoAction]:
        return list((await self.session.execute(select(MatchVetoAction).where(MatchVetoAction.match_series_id == match_id).order_by(MatchVetoAction.order_index))).scalars())

    async def replace(self, match_id: int, actions: list[dict], *, status: str | None = None, source: str = "manual", source_external_id: str | None = None) -> tuple[Match, list[str]]:
        match = await self.session.get(Match, match_id)
        if not match: raise VetoError("Серия не найдена.")
        clean = [{**a, "map_name": normalize_map(a["map_name"])} for a in actions]
        pool = set((await self.session.execute(select(MapPoolEntry.map_name).where(MapPoolEntry.version == match.map_pool_version))).scalars()) if match.map_pool_version else None
        derived, issues = validate_actions(match, clean, pool or None)
        final = status or derived
        if final == "complete" and derived != "complete": raise VetoError("Невалидный veto нельзя отметить complete: " + ", ".join(issues))
        if final not in {"not_available", "complete", "partial", "needs_review", "invalid"}: raise VetoError("Неизвестный veto status.")
        await self.session.execute(delete(MatchVetoAction).where(MatchVetoAction.match_series_id == match_id))
        now = datetime.now(timezone.utc)
        for item in clean:
            team = await self.session.get(Team, item.get("team_id")) if item.get("team_id") else None
            self.session.add(MatchVetoAction(match_series_id=match_id, order_index=item["order_index"], team_id=item.get("team_id"), team_name=team.name if team else item.get("team_name"), action=item["action"], map_name=item["map_name"], source=source, source_external_id=item.get("source_external_id") or source_external_id, source_updated_at=now))
        match.veto_data_status, match.veto_source, match.veto_source_external_id, match.veto_source_updated_at = final, source, source_external_id, now
        await self.session.flush(); await self._apply_roles(match)
        return match, issues

    async def replace_text(self, match_id: int, text: str, *, status: str | None = None) -> tuple[Match, list[str]]:
        match = await self.session.get(Match, match_id)
        if not match: raise VetoError("Серия не найдена.")
        team_a = await self.session.get(Team, match.team_a_id) if match.team_a_id else None
        team_b = await self.session.get(Team, match.team_b_id) if match.team_b_id else None
        return await self.replace(match_id, parse_veto_text(match, team_a, team_b, text),
                                  status=status, source="manual")

    async def _apply_roles(self, match: Match) -> None:
        actions = await self.actions(match.id)
        roles = {a.map_name: a for a in actions if a.action in {"pick", "decider"}}
        rows = (await self.session.execute(select(DemoFile, DemoMapResult).join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id).where(DemoFile.match_id == match.id))).all()
        for demo, result in rows:
            action = roles.get(normalize_map(result.map_name or "")); demo.picked_by_team_id = action.team_id if action and action.action == "pick" else None
            demo.map_role = "decider" if action and action.action == "decider" else "team_pick" if action and action.action == "pick" else "unknown"

    async def profile(self, team_id: int, *, aggregation_level: str = "organization", recent: int | None = None, rank_scope: str | None = None, context: str | None = None, opponent_id: int | None = None) -> dict:
        team = await self.session.get(Team, team_id)
        if not team: raise VetoError("Команда не найдена.")
        q = select(Match).where(or_(Match.team_a_id == team_id, Match.team_b_id == team_id), Match.veto_data_status.in_(("complete", "partial"))).order_by(Match.match_date.desc(), Match.id.desc())
        matches = list((await self.session.execute(q)).scalars())
        if opponent_id: matches = [m for m in matches if opponent_id in {m.team_a_id, m.team_b_id}]
        if context: matches = [m for m in matches if (context == m.environment or context == m.stage or context == "playoff" and m.is_playoff or context == "elimination" and m.is_elimination)]
        if aggregation_level == "current_roster":
            matches = [] if not team.current_roster_id else [m for m in matches if await self._uses_roster(m.id, team_id, team.current_roster_id)]
        if rank_scope: matches = [m for m in matches if await self._rank_ok(m, team_id, rank_scope)]
        if recent: matches = matches[:recent]
        entries = list((await self.session.execute(select(MapPoolEntry))).scalars()); active = {e.map_name for e in entries if e.is_active}
        maps = sorted(VALID_MAPS | {a.map_name for m in matches for a in await self.actions(m.id)})
        breakdown = []
        for map_name in maps:
            eligible = [m for m in matches if not m.map_pool_version or not entries or any(e.version == m.map_pool_version and e.map_name == map_name for e in entries)]
            acts = [(m, a, await self.actions(m.id)) for m in eligible for a in await self.actions(m.id) if a.map_name == map_name]
            bans = [(m,a,all_a) for m,a,all_a in acts if a.action == "ban" and a.team_id == team_id]; picks = [(m,a,all_a) for m,a,all_a in acts if a.action == "pick" and a.team_id == team_id]
            first_bans = [x for x in bans if x[1].order_index == min(a.order_index for a in x[2] if a.team_id == team_id)]
            first_picks = [x for x in picks if x[1].order_index == min(a.order_index for a in x[2] if a.team_id == team_id and a.action == "pick")]
            perf = await self._performance(eligible, team_id, map_name)
            n, freshness = len(eligible), (1 if not eligible else exp(-max(0, (date.today()-eligible[0].match_date).days)/180))
            ban_rate, pick_rate = rate(len(bans), n), rate(len(picks), n)
            permaban = min(100.0, (0.65*(rate(len(first_bans), n) or 0)+0.35*(ban_rate or 0))*min(1,n/8)*freshness)
            preference = min(100.0, (0.65*(pick_rate or 0)+0.35*(rate(len(first_picks), n) or 0))*freshness)
            breakdown.append({"map_name": map_name, "active": map_name in active if entries else True, "eligible_series": n, "veto_appearances": len(acts), "ban":{"count":len(bans),"rate":ban_rate,"first_ban_count":len(first_bans),"first_ban_rate":rate(len(first_bans),n)}, "pick":{"count":len(picks),"rate":pick_rate,"first_pick_count":len(first_picks),"first_pick_rate":rate(len(first_picks),n), **perf["own"]}, "opponent_pick":perf["opponent"], "decider":perf["decider"], "is_likely_permaban":n>=5 and permaban>=60, "permaban_confidence":round(permaban,2), "pick_preference_score":round(preference,2) if n else None})
        complete = sum(m.veto_data_status == "complete" for m in matches); confidence = min(100, len(matches)*8) * .45 + freshness*100*.3 + (complete/len(matches)*100 if matches else 0)*.25
        return {"team_id":team.id,"team_name":team.name,"aggregation_level":aggregation_level,"roster_id":team.current_roster_id if aggregation_level=="current_roster" else None,"sample":{"series":len(matches),"complete_series":complete},"veto_confidence":round(confidence,2) if matches else 0,"denominator":"eligible series with complete/partial veto and map in the series map-pool version; when version is unknown, every valid-veto series", "maps":breakdown}

    async def _uses_roster(self, match_id:int, team_id:int, roster_id:int)->bool:
        demos=list((await self.session.execute(select(DemoFile.id).where(DemoFile.match_id==match_id))).scalars())
        if not demos:return False
        rows=list((await self.session.execute(select(DemoTeamRoster).where(DemoTeamRoster.demo_file_id.in_(demos),DemoTeamRoster.team_id==team_id))).scalars())
        return len(rows)==len(demos) and all(r.resolution_status=="complete" and r.roster_id==roster_id for r in rows)
    async def _rank_ok(self,m:Match,team_id:int,scope:str)->bool:
        demos=list((await self.session.execute(select(DemoFile.id).where(DemoFile.match_id==m.id))).scalars())
        groups=set((await self.session.execute(select(DemoTeamOpponentContext.opponent_rank_group).where(DemoTeamOpponentContext.demo_file_id.in_(demos),DemoTeamOpponentContext.team_id==team_id))).scalars())
        return scope in groups
    async def _performance(self,matches:list[Match],team_id:int,map_name:str)->dict:
        out={k:{"maps":0,"wins":0,"losses":0,"win_rate":None} for k in ("own","opponent","decider")}
        for m in matches:
            action=next((a for a in await self.actions(m.id) if a.map_name==map_name and a.action in {"pick","decider"}),None)
            if not action:continue
            key="decider" if action.action=="decider" else "own" if action.team_id==team_id else "opponent"
            rows=(await self.session.execute(select(DemoFile,DemoMapResult).join(DemoMapResult,DemoMapResult.demo_file_id==DemoFile.id).where(DemoFile.match_id==m.id,DemoMapResult.map_name==map_name))).all()
            for demo,result in rows:
                scores=(result.team_a_score,result.team_b_score); won=(result.team_a_id==team_id and scores[0]>scores[1]) or (result.team_b_id==team_id and scores[1]>scores[0])
                out[key]["maps"]+=1; out[key]["wins" if won else "losses"]+=1
        for x in out.values():x["win_rate"]=rate(x["wins"],x["maps"])
        return out

async def comparison(session:AsyncSession,a:int,b:int,aggregation_level:str="current_roster")->dict:
    service=VetoService(session); pa=await service.profile(a,aggregation_level=aggregation_level); pb=await service.profile(b,aggregation_level=aggregation_level)
    ia={x["map_name"]:x for x in pa["maps"]}; ib={x["map_name"]:x for x in pb["maps"]}; rows=[]
    for name in sorted(set(ia)|set(ib)):
        x,y=ia.get(name),ib.get(name); ap=x and x["pick_preference_score"]; bb=y and y["permaban_confidence"]
        score=max((ap or 0)*(bb or 0)/100,(y and y["pick_preference_score"] or 0)*(x and x["permaban_confidence"] or 0)/100)
        collision="unknown" if not x or not y or not x["eligible_series"] or not y["eligible_series"] else "high" if score>=55 else "medium" if score>=30 else "low"
        availability="unknown" if collision=="unknown" else "likely_removed" if max(x["ban"]["rate"] or 0,y["ban"]["rate"] or 0)>=60 else "contested" if collision in {"high","medium"} else "likely_available"
        rows.append({"map_name":name,"team_a":x,"team_b":y,"collision":collision,"availability":availability})
    h2h_a=await service.profile(a,aggregation_level="organization",recent=3,opponent_id=b)
    return {"team_a":pa,"team_b":pb,"maps":rows,"h2h":{"series":h2h_a["sample"]["series"],"maps":h2h_a["maps"]}}
