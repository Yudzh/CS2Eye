from __future__ import annotations

from datetime import date,timedelta
from math import exp
from sqlalchemy import or_,select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.opponent_context_config import ADJUSTED_FORM_VERSION,OPPONENT_CONTEXT_CONFIG,OPPONENT_CONTEXT_VERSION
from cs2eye.models.match import Match
from cs2eye.models.team import Team,TeamRankingSnapshot
from cs2eye.services.form_context_service import FormContextService,clamp,rank_strength


class OpponentContextService:
    """Depth-1 opponent state. Every input uses rows strictly before its as_of date."""
    def __init__(self,session:AsyncSession):self.session=session;self._strength_cache={};self._context_cache={}

    async def dynamic_strength(self,team_id:int,as_of:date,tournament_id:int|None=None)->dict:
        key=(team_id,as_of,tournament_id,OPPONENT_CONTEXT_VERSION)
        if key in self._strength_cache:return self._strength_cache[key]
        form=await FormContextService(self.session).calculate(team_id,as_of,tournament_id)
        rank=(await self.session.scalars(select(TeamRankingSnapshot).where(TeamRankingSnapshot.team_id==team_id,TeamRankingSnapshot.ranking_date<=as_of).order_by(TeamRankingSnapshot.ranking_date.desc(),TeamRankingSnapshot.id.desc()).limit(1))).first()
        ranking=rank_strength(rank.rank) if rank else None
        # The temporal Elo fallback used by FormContext is the deterministic base when
        # no separately snapshotted Team Strength artifact exists for this date.
        elo=await FormContextService(self.session)._elo_before(as_of,{team_id})
        latest=next((value for (match_id,current_team),value in reversed(list(elo.items())) if current_team==team_id),None)
        base=FormContextService._elo_strength(latest) if latest is not None else ranking
        components={"base_team_strength":base,"ranking_strength":ranking,"recent_form":form.get("recent_60d_adjusted_form_score"),"tournament_form":form.get("tournament_form_score") if form.get("tournament_matches_count",0)>0 else None,"strength_of_schedule":form.get("strength_of_schedule_score"),"performance_expectation":form.get("performance_vs_expectation_score")}
        available={name:value for name,value in components.items() if value is not None};configured=OPPONENT_CONTEXT_CONFIG.component_weights;total=sum(configured[name] for name in available)
        raw=sum(float(value)*configured[name] for name,value in available.items())/total if total else 50.
        count=int(form.get("recent_60d_matches_count",0));sample=min(1.,count/OPPONENT_CONTEXT_CONFIG.target_sample)
        availability=sum(configured[name] for name in available);freshness=await self._freshness(team_id,as_of)
        reliability=min(1.,sample*.55+availability*.30+freshness*.15)
        score=50+(raw-50)*reliability
        result={"version":OPPONENT_CONTEXT_VERSION,"team_id":team_id,"as_of":as_of,"score":round(clamp(score),2),"raw_score":round(clamp(raw),2),"reliability":round(reliability,4),"components":components,"matches_count":count,"depth":1,"tournament_data_available":components["tournament_form"] is not None}
        self._strength_cache[key]=result;return result

    async def calculate(self,team_id:int,as_of:date|None=None,tournament_id:int|None=None)->dict:
        as_of=as_of or date.today();key=(team_id,as_of,tournament_id,OPPONENT_CONTEXT_VERSION)
        if key in self._context_cache:return self._context_cache[key]
        matches=list((await self.session.scalars(select(Match).where(or_(Match.team_a_id==team_id,Match.team_b_id==team_id),Match.match_date<as_of,Match.match_date>=as_of-timedelta(days=OPPONENT_CONTEXT_CONFIG.window_days),Match.status=="completed",Match.winner_team_id.is_not(None)).order_by(Match.match_date.desc(),Match.id.desc()))).all())
        opponent_ids={m.team_b_id if m.team_a_id==team_id else m.team_a_id for m in matches}-{None};teams={x.id:x for x in (await self.session.scalars(select(Team).where(Team.id.in_(opponent_ids)))).all()}
        rows=[]
        for match in matches:
            opponent_id=match.team_b_id if match.team_a_id==team_id else match.team_a_id
            if opponent_id is None:continue
            dynamic=await self.dynamic_strength(opponent_id,match.match_date,match.tournament_id)
            won=match.winner_team_id==team_id;strength=dynamic["score"];base=(.2+.8*strength/100) if won else -(.2+.8*(100-strength)/100)
            own=match.team_a_maps_won if match.team_a_id==team_id else match.team_b_maps_won;other=match.team_b_maps_won if match.team_a_id==team_id else match.team_a_maps_won
            dominance=abs(own-other)/max(1,own+other);base+=(1 if won else -1)*OPPONENT_CONTEXT_CONFIG.margin_modifier*dominance
            freshness=exp(-max(0,(as_of-match.match_date).days)/OPPONENT_CONTEXT_CONFIG.decay_days)
            if tournament_id is not None and match.tournament_id==tournament_id:freshness*=OPPONENT_CONTEXT_CONFIG.tournament_multiplier
            quality=max(-1.,min(1.,base))*freshness*(.5+.5*dynamic["reliability"])
            rows.append({"match_id":match.id,"date":match.match_date,"opponent":{"id":opponent_id,"name":teams.get(opponent_id).name if teams.get(opponent_id) else None},"result":"win" if won else "loss","series_score":f"{own}-{other}","opponent_dynamic_strength":strength,"opponent_reliability":dynamic["reliability"],"result_quality_score":round(quality,4),"result_quality_label":self._label(quality,won),"current_tournament":tournament_id is not None and match.tournament_id==tournament_id})
        total=sum(exp(-max(0,(as_of-row["date"]).days)/OPPONENT_CONTEXT_CONFIG.decay_days) for row in rows)
        adjusted=50 if not total else clamp(50+sum(row["result_quality_score"] for row in rows)/total*50)
        raw=50 if not rows else sum(100 if row["result"]=="win" else 0 for row in rows)/len(rows)
        tournament_rows=[row for row in rows if row["current_tournament"]]
        tournament_adjusted=None if not tournament_rows else clamp(50+sum(row["result_quality_score"] for row in tournament_rows)/len(tournament_rows)*50)
        result={"version":OPPONENT_CONTEXT_VERSION,"adjusted_form_version":ADJUSTED_FORM_VERSION,"team_id":team_id,"team":(await self.session.get(Team,team_id)).name if await self.session.get(Team,team_id) else None,"as_of":as_of,"tournament_id":tournament_id,"matches":rows,"raw_form_score":round(raw,2),"opponent_adjusted_form_score":round(adjusted,2),"tournament_opponent_adjusted_form_score":None if tournament_adjusted is None else round(tournament_adjusted,2),"dynamic_sos_score":None if not rows else round(sum(row["opponent_dynamic_strength"] for row in rows)/len(rows),2),"reliability":round(min(1,len(rows)/OPPONENT_CONTEXT_CONFIG.target_sample)*(.5+.5*(sum(row["opponent_reliability"] for row in rows)/len(rows) if rows else 0)),4),"cutoff_policy":"event_date < as_of","depth":1,"candidate":True}
        self._context_cache[key]=result;return result

    async def _freshness(self,team_id:int,as_of:date)->float:
        latest=(await self.session.scalars(select(Match.match_date).where(or_(Match.team_a_id==team_id,Match.team_b_id==team_id),Match.match_date<as_of,Match.status=="completed").order_by(Match.match_date.desc()).limit(1))).first()
        return 0. if latest is None else exp(-max(0,(as_of-latest).days)/OPPONENT_CONTEXT_CONFIG.decay_days)

    @staticmethod
    def _label(value:float,won:bool)->str:
        if won:return "strong_win" if value>=.55 else "expected_win" if value>=.3 else "low_value_win"
        return "acceptable_loss" if value>=-.35 else "bad_loss" if value<=-.55 else "loss"
