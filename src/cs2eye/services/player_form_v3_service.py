from __future__ import annotations
from datetime import date,timedelta
from math import sqrt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.analytics.team_form_v3_config import DELTA_LIMIT,PLAYER_MODEL_VERSION,PLAYER_WEIGHTS
from cs2eye.models.demo import DemoParseRun,DemoPlayerStat
from cs2eye.models.demo_file import DemoFile

def _ratio(a,b):return a/b if b else None
def _raw(rows):
 rounds=sum(x.rounds_played for x in rows);kills=sum(x.kills for x in rows);deaths=sum(x.deaths for x in rows);damage=sum(float(x.total_damage) for x in rows)
 combat=[x.combat_data for x in rows if x.combat_data];utility=[x.utility_data for x in rows if x.utility_data]
 def total(values,key):return sum(float(x.get(key,0) or 0) for x in values)
 openings=total(combat,"opening_kills")+total(combat,"opening_deaths");trade_opps=total(combat,"trade_opportunities")
 flashes=total(utility,"flash_thrown");utility_rounds=total(utility,"rounds_played")
 u=[_ratio(total(utility,"flash_assists"),utility_rounds),_ratio(total(utility,"enemies_flashed"),flashes),_ratio(total(utility,"utility_damage"),utility_rounds)];u=[x for x in u if x is not None]
 return {"rounds":rounds,"maps":len(rows),"kills_per_round":_ratio(kills,rounds),"adr":_ratio(damage,rounds),"survival_rate":_ratio(max(0,rounds-deaths),rounds),"opening":_ratio(total(combat,"opening_kills"),openings),"trading":_ratio(total(combat,"trade_kills"),trade_opps),"utility":sum(u)/len(u) if u else None}

# Unit sensitivities translate self-relative raw changes into a common delta;
# this is deliberately not league normalization or absolute strength.
SENSITIVITY={"kills_per_round":80.,"adr":.45,"survival_rate":70.,"opening":55.,"trading":55.,"utility":18.}

class PlayerFormV3Service:
 def __init__(self,session:AsyncSession):self.session=session;self._rows={}
 async def calculate(self,player_id:int,as_of:date|None=None)->dict:
  cutoff=as_of or date.today();since=cutoff-timedelta(days=60);baseline_since=since-timedelta(days=180);cache_key=(player_id,cutoff)
  if cache_key not in self._rows:
   query=(select(DemoPlayerStat,DemoFile.match_date).join(DemoParseRun,DemoParseRun.id==DemoPlayerStat.parse_run_id).join(DemoFile,DemoFile.id==DemoPlayerStat.demo_file_id).where(DemoParseRun.status=="success",DemoPlayerStat.player_id==player_id,DemoFile.match_date>=baseline_since,DemoFile.match_date<cutoff))
   self._rows[cache_key]=(await self.session.execute(query)).all()
  pairs=self._rows[cache_key];recent=_raw([x for x,d in pairs if d>=since]);baseline=_raw([x for x,d in pairs if d<since]);metrics={}
  for key,weight in PLAYER_WEIGHTS.items():
   now=recent.get(key);normal=baseline.get(key);delta=None if now is None or normal is None else max(-25.,min(25.,(now-normal)*SENSITIVITY[key]))
   metrics[key]={"delta":None if delta is None else round(delta,2),"recent_value":now,"baseline_value":normal,"weight":weight,"sample_size":recent["rounds"]}
  def block(keys):
   values=[metrics[x] for x in keys if metrics[x]["delta"] is not None];total=sum(x["weight"] for x in values)
   return round(sum(x["delta"]*x["weight"]/total for x in values),2) if total else None
  mechanical=block(("kills_per_round","adr","survival_rate"));supporting=block(("opening","trading","utility"));values=[x for x in metrics.values() if x["delta"] is not None];total=sum(x["weight"] for x in values)
  delta=sum(x["delta"]*x["weight"]/total for x in values) if total else 0.;map_factor=min(1.,recent["maps"]/12);round_factor=min(1.,recent["rounds"]/240);baseline_factor=min(1.,baseline["maps"]/20);coverage=len(values)/len(PLAYER_WEIGHTS)
  reliability=100*sqrt(map_factor*round_factor)*(.4+.6*baseline_factor)*coverage;delta=max(-DELTA_LIMIT,min(DELTA_LIMIT,delta));score=max(0.,min(100.,50+2*delta))
  return {"score":round(score,2),"delta":round(delta,2),"form_score":round(score,2),"form_delta":round(delta,2),"reliability":round(reliability,1),"model_version":PLAYER_MODEL_VERSION,"as_of":cutoff,"mechanical_form":{"delta":mechanical,"reliability":round(reliability,1)},"supporting_form":{"delta":supporting,"reliability":round(reliability,1)},"metrics":metrics,"sample":{"maps":recent["maps"],"rounds":recent["rounds"],"baseline_maps":baseline["maps"]},"bo3_rating_excluded":True}
