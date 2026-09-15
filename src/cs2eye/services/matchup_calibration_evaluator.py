from __future__ import annotations
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG,MatchupModelConfig
from cs2eye.analytics.matchup_engine import apply_config_to_payload
from cs2eye.models.match import Match
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService

MARGIN_BUCKETS=(("0-5",0,5),("5-10",5,10),("10-20",10,20),("20+",20,float("inf")))

class MatchupCalibrationEvaluator:
    def __init__(self,session:AsyncSession,minimum_sample:int=30):self.session=session;self.minimum_sample=minimum_sample

    async def evaluate(self,*,limit:int=120,baseline:MatchupModelConfig=ACTIVE_MATCHUP_CONFIG,candidate:MatchupModelConfig=ACTIVE_MATCHUP_CONFIG)->dict:
        matches=list((await self.session.scalars(select(Match).where(Match.status=="completed",Match.winner_team_id.is_not(None),Match.team_a_id.is_not(None),Match.team_b_id.is_not(None)).order_by(Match.match_date.desc(),Match.id.desc()).limit(limit))).all())
        examples,dataset_meta=await AnalyticsAsOfService(self.session).build_dataset_v3("pre_veto")
        by_id={x.series_id:x for x in examples};rows=[]
        for match in matches:
            example=by_id.get(match.id)
            if example is None:continue
            payload={**example.matchup,"factors":list(example.matchup["factors"])}
            available=[x for x in payload["factors"] if x.get("available",True) and x.get("score") is not None and x["key"] in baseline.factors]
            payload["reliability"]=sum((float(x.get("confidence") or 0))*baseline.factors[x["key"]].weight for x in available)/sum(baseline.factors[x["key"]].weight for x in available) if available else 0
            a=apply_config_to_payload(payload,baseline);b=apply_config_to_payload(payload,candidate)
            rows.append({"match":match,"baseline":a,"candidate":b,"actual":match.winner_team_id})
        baseline_report=self._model_report(rows,"baseline",baseline.version);candidate_report=self._model_report(rows,"candidate",candidate.version)
        flips=[];lost_predictions=[];new_predictions=[];fixed=broken=0
        for row in rows:
            a=row["baseline"];b=row["candidate"]
            aw=a["advantage"]["team_id"];bw=b["advantage"]["team_id"]
            if aw==bw:continue
            ac=a["advantage"]["team_id"]==row["actual"];bc=b["advantage"]["team_id"]==row["actual"]
            changes=[]
            af={x["key"]:x for x in a["factors"]};bf={x["key"]:x for x in b["factors"]}
            for key in af.keys()|bf.keys():
                old=self._final_contribution(a,af.get(key,{}));new=self._final_contribution(b,bf.get(key,{}))
                if abs(old-new)>.01:changes.append({"factor":key,"baseline_contribution":old,"candidate_contribution":new,"change":new-old})
            changes.sort(key=lambda x:abs(x["change"]),reverse=True)
            match=row["match"];item={"match_id":match.id,"match":f"{a['team_a'].get('name',match.team_a_id)} vs {a['team_b'].get('name',match.team_b_id)}","baseline_winner_id":aw,"candidate_winner_id":bw,"actual_winner_id":row["actual"],"baseline_score":a["team_a"]["score"],"candidate_score":b["team_a"]["score"],"main_changed_factors":changes[:3]}
            if aw is not None and bw is None:
                lost_predictions.append({**item,"baseline_was_correct":ac})
            elif aw is None and bw is not None:
                new_predictions.append({**item,"candidate_is_correct":bc})
            elif aw is not None and bw is not None:
                fixed+=int(not ac and bc);broken+=int(ac and not bc)
                flips.append({**item,"result":"fixed" if not ac and bc else "broken" if ac and not bc else "changed"})
        gate=self._gate(baseline_report,candidate_report)
        return {"baseline":baseline_report,"candidate":candidate_report,"delta":{"accuracy":None if baseline_report["accuracy"] is None or candidate_report["accuracy"] is None else candidate_report["accuracy"]-baseline_report["accuracy"]},"flips":{"total":len(flips),"v2_fixed_v1_error":fixed,"v2_broke_v1_correct":broken,"net_improvement":fixed-broken,"matches":flips},"abstention_changes":{"lost_predictions":len(lost_predictions),"lost_correct_predictions":sum(x["baseline_was_correct"] for x in lost_predictions),"avoided_baseline_errors":sum(not x["baseline_was_correct"] for x in lost_predictions),"new_predictions":len(new_predictions),"new_correct_predictions":sum(x["candidate_is_correct"] for x in new_predictions),"new_incorrect_predictions":sum(not x["candidate_is_correct"] for x in new_predictions),"lost_prediction_matches":lost_predictions,"new_prediction_matches":new_predictions},"factor_impact_comparison":self._impact_comparison(rows),"sample_size":len(rows),"dataset":dataset_meta,"gate_status":gate[0],"gate_checks":gate[1]}

    def _model_report(self,rows,key,version):
        evaluable=[r for r in rows if r[key]["advantage"]["team_id"] is not None];correct=sum(r[key]["advantage"]["team_id"]==r["actual"] for r in rows)
        margins=[abs(r[key]["team_a"]["score"]-r[key]["team_b"]["score"]) for r in evaluable]
        buckets={}
        for name,low,high in MARGIN_BUCKETS:
            group=[r for r in evaluable if low<=abs(r[key]["team_a"]["score"]-r[key]["team_b"]["score"])<high];wins=sum(r[key]["advantage"]["team_id"]==r["actual"] for r in group)
            buckets[name]={"samples":len(group),"accuracy":None if not group else wins/len(group)}
        predictions=len(evaluable);matches=len(rows)
        return {"version":version,"matches":matches,"predictions":predictions,"abstentions":matches-predictions,"coverage":None if not matches else predictions/matches,"correct":correct,"accuracy":None if not predictions else correct/predictions,"overall_correct_rate":None if not matches else correct/matches,"average_winner_margin":None if not margins else sum(margins)/len(margins),"low_margin_accuracy":buckets["0-5"]["accuracy"],"high_margin_accuracy":self._combined(buckets,"10-20","20+"),"margin_buckets":buckets,"error_drivers":self._error_drivers(evaluable,key),"factor_quality":self._factor_quality(rows,key)}

    @staticmethod
    def _combined(buckets,*keys):
        samples=sum(buckets[k]["samples"] for k in keys);return None if not samples else sum((buckets[k]["accuracy"] or 0)*buckets[k]["samples"] for k in keys)/samples

    @staticmethod
    def _error_drivers(rows,key):
        out=defaultdict(int)
        for r in rows:
            model=r[key];winner=model["advantage"]["team_id"]
            if winner==r["actual"]:continue
            direction=1 if winner==model["team_a"]["id"] else -1
            drivers=[x for x in model["factors"] if float(x.get("impact") or 0)*direction>0]
            if drivers:out[max(drivers,key=lambda x:abs(float(x.get("impact") or 0)))["key"]]+=1
        return dict(out)

    @staticmethod
    def _impact_comparison(rows):
        values=defaultdict(lambda:{"baseline":[],"candidate":[]})
        for row in rows:
            for side in ("baseline","candidate"):
                for factor in row[side]["factors"]:values[factor["key"]][side].append(abs(MatchupCalibrationEvaluator._final_contribution(row[side],factor)))
        return {key:{"baseline_average_absolute_contribution":sum(x["baseline"])/len(x["baseline"]) if x["baseline"] else None,"candidate_average_absolute_contribution":sum(x["candidate"])/len(x["candidate"]) if x["candidate"] else None} for key,x in sorted(values.items())}

    @staticmethod
    def _final_contribution(model,factor):
        return float(factor.get("impact") or 0)*float(model.get("reliability") or 0)

    @staticmethod
    def _factor_quality(rows,key):
        values=defaultdict(list)
        for row in rows:
            model=row[key];a=model["team_a"]["id"]
            for factor in model["factors"]:
                score=factor.get("score")
                if score is None or float(score)==50:continue
                direction=a if float(score)>50 else model["team_b"]["id"]
                values[factor["key"]].append((direction==row["actual"],factor.get("confidence")))
        out={}
        for factor,items in sorted(values.items()):
            buckets={}
            for name,low,high in (("low",0,.45),("medium",.45,.75),("high",.75,1.0001)):
                group=[x for x in items if x[1] is not None and low<=float(x[1])<high]
                buckets[name]={"samples":len(group),"direction_accuracy":None if not group else sum(x[0] for x in group)/len(group)}
            out[factor]={"directional_cases":len(items),"direction_correct":sum(x[0] for x in items),"direction_accuracy":sum(x[0] for x in items)/len(items),"reliability":buckets}
        return out

    def _gate(self,baseline,candidate):
        def violations(report):
            values=[report["margin_buckets"][name]["accuracy"] for name,_,_ in MARGIN_BUCKETS];present=[x for x in values if x is not None]
            return sum(right+.05<left for left,right in zip(present,present[1:]))
        checks={"sufficient_sample":candidate["matches"]>=self.minimum_sample,"produces_predictions":candidate["predictions"]>0,"coverage_not_collapsed":candidate["coverage"] is not None and baseline["coverage"] is not None and candidate["coverage"]>=baseline["coverage"]*.9,"accuracy_not_worse":candidate["accuracy"] is not None and baseline["accuracy"] is not None and candidate["accuracy"]>=baseline["accuracy"],"high_margin_not_materially_worse":candidate["high_margin_accuracy"] is None or baseline["high_margin_accuracy"] is None or candidate["high_margin_accuracy"]>=baseline["high_margin_accuracy"]-.05,"margin_shape_not_worse":violations(candidate)<=violations(baseline)}
        if not checks["sufficient_sample"]:return "insufficient_sample",checks
        return ("passed" if all(checks.values()) else "failed"),checks
