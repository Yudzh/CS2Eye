from __future__ import annotations
from datetime import UTC,date,datetime
from decimal import Decimal
import numpy as np
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.analytics.win_probability import WinProbabilityModel,probability_metrics,temporal_split
from cs2eye.analytics.win_probability_config import MIN_PREDICTION_CONFIDENCE,WIN_PROBABILITY_FEATURES,WIN_PROBABILITY_FEATURE_SCHEMA_VERSION,WIN_PROBABILITY_MODEL_VERSION
from cs2eye.models.prediction import MatchPrediction,WinProbabilityModelArtifact
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.matchup_service import MatchupService
from cs2eye.models.team import Team

async def active_model(session):return (await session.execute(select(WinProbabilityModelArtifact).where(WinProbabilityModelArtifact.is_active.is_(True)).order_by(WinProbabilityModelArtifact.trained_at.desc()))).scalars().first()


def _feature_vector(matchup:dict,format:str,ranking_advantage:float=0.0)->dict[str,float]:
    factors={item["key"]:item for item in matchup.get("factors",[])}
    def centered(key:str)->float:
        score=(factors.get(key) or {}).get("score")
        return 0.0 if score is None else (float(score)-50.0)/50.0
    strength=centered("team_strength")
    values={
        "matchup_score_centered":(float(matchup["team_a"]["score"])-50.0)/50.0,
        "raw_matchup_centered":(float(matchup["raw_score"])-50.0)/50.0,
        "matchup_reliability_advantage":(float(matchup["team_a"]["score"])-50.0)/50.0*float(matchup.get("reliability",0)),
        "team_strength_difference":strength,
        "map_pool_advantage":centered("map_veto"),
        "current_roster_advantage":centered("current_roster_form"),
        "tactical_advantage":centered("tactical_matchup"),
        "h2h_advantage":centered("h2h"),
        "leadership_advantage":centered("leadership_context"),
        "ranking_advantage":ranking_advantage,
        "format_bo1_strength":strength if format=="bo1" else 0.0,
        "format_bo3_strength":strength if format=="bo3" else 0.0,
        "format_bo5_strength":strength if format=="bo5" else 0.0,
    }
    return {key:float(values[key]) for key in WIN_PROBABILITY_FEATURES}

def _distribution(values):
    a=np.asarray(values,float);return {"min":float(a.min()),"p10":float(np.percentile(a,10)),"p25":float(np.percentile(a,25)),"median":float(np.median(a)),"p75":float(np.percentile(a,75)),"p90":float(np.percentile(a,90)),"max":float(a.max())} if len(a) else {}

async def train_win_probability(session:AsyncSession,mode:str="pre_veto")->dict:
    rows,report=await AnalyticsAsOfService(session).build_dataset(mode);train,validation,test=temporal_split(rows)
    if not test or not validation:raise ValueError("Insufficient chronological series for train/validation/test.")
    model=WinProbabilityModel.train([x.features for x in train],[x.target for x in train]);metrics={"train":probability_metrics(model.predict_symmetric([x.features for x in train]),[x.target for x in train]),"validation":probability_metrics(model.predict_symmetric([x.features for x in validation]),[x.target for x in validation]),"test":probability_metrics(model.predict_symmetric([x.features for x in test]),[x.target for x in test])}
    def baseline(name,pred):return {name:probability_metrics(pred,[x.target for x in test])}
    baselines={**baseline("neutral_50",[.5]*len(test))}
    for name,key in (("team_strength","team_strength_difference"),("matchup_score","matchup_score_centered")):
        bm=WinProbabilityModel.train([{k:(x.features[key] if k==key else 0) for k in WIN_PROBABILITY_FEATURES} for x in train],[x.target for x in train]);baselines.update(baseline(name,bm.predict_symmetric([{k:(x.features[key] if k==key else 0) for k in WIN_PROBABILITY_FEATURES} for x in test])))
    predictions=model.predict_symmetric([x.features for x in test]);metadata={"split":{"strategy":"70_15_15_chronological","training_series":len(train),"validation_series":len(validation),"test_series":len(test),"train_dates":[train[0].match_date.isoformat(),train[-1].match_date.isoformat()],"validation_dates":[validation[0].match_date.isoformat(),validation[-1].match_date.isoformat()],"test_dates":[test[0].match_date.isoformat(),test[-1].match_date.isoformat()]},"metrics":metrics,"baselines":baselines,"probability_distribution":_distribution(predictions),"extremes":{"below_20":sum(p<.2 for p in predictions),"above_80":sum(p>.8 for p in predictions)},"coefficients":dict(zip(WIN_PROBABILITY_FEATURES,model.artifact["coefficients"])),"coverage":report,"calibration_method":"raw_logistic","strict_historical":True}
    row=WinProbabilityModelArtifact(model_version=WIN_PROBABILITY_MODEL_VERSION,feature_schema_version=WIN_PROBABILITY_FEATURE_SCHEMA_VERSION,trained_at=datetime.now(UTC),training_series=len(train),validation_series=len(validation),test_series=len(test),artifact=model.artifact,metrics=metadata,dataset_report=report,is_active=False);session.add(row);await session.flush();return {"artifact_id":row.id,"activated":False,**metadata}

async def activate_win_probability(session:AsyncSession,artifact_id:int,force:bool=False)->dict:
    row=await session.get(WinProbabilityModelArtifact,artifact_id)
    if not row:raise ValueError("Model artifact not found.")
    test=row.metrics.get("metrics",{}).get("test",{})
    baselines=row.metrics.get("baselines",{})
    baseline_rows=[value for value in baselines.values() if isinstance(value,dict)]
    best_log=min((float(value["log_loss"]) for value in baseline_rows if value.get("log_loss") is not None),default=float("inf"))
    best_brier=min((float(value["brier_score"]) for value in baseline_rows if value.get("brier_score") is not None),default=float("inf"))
    if not force and float(test.get("log_loss",float("inf")))>=best_log and float(test.get("brier_score",float("inf")))>=best_brier:
        raise ValueError("Candidate does not outperform the best baseline on Log Loss or Brier; activation rejected.")
    await session.execute(update(WinProbabilityModelArtifact).values(is_active=False));row.is_active=True;await session.flush();return {"artifact_id":row.id,"model_version":row.model_version,"active":True}

async def predict_win_probability(session:AsyncSession,a:int,b:int,format:str="bo3",mode:str="pre_veto",as_of:date|None=None,series_id:int|None=None)->dict:
    artifact=await active_model(session)
    if not artifact:return {"prediction_status":"model_not_trained","model_version":None,"team_a":{"id":a,"probability":None},"team_b":{"id":b,"probability":None},"confidence":0,"limitations":[]}
    cutoff=as_of or date.today();historical=cutoff<date.today()
    matchup=await (AnalyticsAsOfService(session).calculate(a,b,cutoff,format,mode,series_id) if historical else MatchupService(session).calculate(a,b,format,mode,cutoff,series_id))
    if historical:
        features=matchup.get("prediction_features") or _feature_vector(matchup,format)
    else:
        teams=list((await session.execute(select(Team).where(Team.id.in_((a,b))))).scalars())
        indexed={team.id:team for team in teams};rank_a=indexed.get(a).current_rank if indexed.get(a) else None;rank_b=indexed.get(b).current_rank if indexed.get(b) else None
        rank_advantage=0.0 if rank_a is None or rank_b is None else max(-30,min(30,rank_b-rank_a))/30
        features=_feature_vector(matchup,format,rank_advantage)
    confidence=matchup.get("reliability",0);status="insufficient_data" if confidence<MIN_PREDICTION_CONFIDENCE else "available";p=WinProbabilityModel(artifact.artifact).predict_symmetric([features])[0] if status=="available" else None
    return {"model_version":artifact.model_version,"feature_schema_version":artifact.feature_schema_version,"trained_at":artifact.trained_at,"prediction_status":status,"team_a":{"id":a,"name":matchup.get("team_a",{}).get("name"),"probability":p},"team_b":{"id":b,"name":matchup.get("team_b",{}).get("name"),"probability":None if p is None else 1-p},"confidence":confidence,"basis":{"analysis_mode":mode,"veto":"actual_veto" if mode=="post_veto" else "calculated_veto","matchup_score":matchup["team_a"]["score"]},"features":features,"matchup":matchup,"limitations":matchup.get("limitations",[])}

async def save_prediction(session:AsyncSession,**kwargs)->dict:
    result=await predict_win_probability(session,**kwargs)
    if result["prediction_status"]!="available":return result
    row=MatchPrediction(series_id=kwargs.get("series_id"),as_of=kwargs.get("as_of") or date.today(),mode=kwargs.get("mode","pre_veto"),source="live_saved_prediction",model_version=result["model_version"],feature_schema_version=result["feature_schema_version"],team_a_id=kwargs["a"],team_b_id=kwargs["b"],team_a_probability=Decimal(str(result["team_a"]["probability"])),team_b_probability=Decimal(str(result["team_b"]["probability"])),confidence=Decimal(str(result["confidence"])),feature_snapshot={"features":result["features"],"basis":result["basis"]},prediction_status="available");session.add(row);await session.flush();return {**result,"prediction_id":row.id}


async def backtest_win_probability(session:AsyncSession,mode:str="pre_veto",artifact_id:int|None=None)->dict:
    artifact=await session.get(WinProbabilityModelArtifact,artifact_id) if artifact_id else await active_model(session)
    if artifact is None:raise ValueError("No active Win Probability model.")
    rows,coverage=await AnalyticsAsOfService(session).build_dataset(mode);_,_,test=temporal_split(rows)
    model=WinProbabilityModel(artifact.artifact);probabilities=model.predict_symmetric([item.features for item in test])
    return {"model_version":artifact.model_version,"feature_schema_version":artifact.feature_schema_version,"analysis_mode":mode,"test_series":len(test),"metrics":probability_metrics(probabilities,[item.target for item in test]),"coverage":coverage,"probability_distribution":_distribution(probabilities)}


async def win_probability_status(session:AsyncSession)->dict:
    active=await active_model(session)
    rows=list((await session.execute(select(WinProbabilityModelArtifact).order_by(WinProbabilityModelArtifact.trained_at.desc()))).scalars())
    return {"active":None if active is None else {"id":active.id,"model_version":active.model_version,"feature_schema_version":active.feature_schema_version,"trained_at":active.trained_at,"metrics":active.metrics},"artifacts":[{"id":row.id,"model_version":row.model_version,"trained_at":row.trained_at,"is_active":row.is_active,"test_series":row.test_series,"metrics":row.metrics.get("metrics",{}).get("test",{})} for row in rows]}
