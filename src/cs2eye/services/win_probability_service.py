from __future__ import annotations
from datetime import UTC,date,datetime
from decimal import Decimal
import numpy as np
from sqlalchemy import func,select,update
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.analytics.win_probability import WinProbabilityModel,probability_metrics,temporal_split
from cs2eye.analytics.win_probability_config import MIN_PREDICTION_CONFIDENCE,WIN_PROBABILITY_FEATURES,WIN_PROBABILITY_FEATURES_V3,WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3,WIN_PROBABILITY_MODEL_VERSION
from cs2eye.models.prediction import MatchPrediction,WinProbabilityModelArtifact
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.matchup_service import MatchupService
from cs2eye.models.team import Team

FEATURE_LABELS={
    "matchup_score_centered":"Matchup Score","raw_matchup_centered":"Raw Matchup Score",
    "matchup_reliability_advantage":"Matchup с учётом надёжности","team_strength_difference":"Team Strength",
    "map_pool_advantage":"Map Pool",
    "tactical_advantage":"Тактическое соответствие","h2h_advantage":"Личные встречи",
    "ranking_advantage":"Рейтинг","tournament_form_advantage":"Tournament Form",
    "recent_60d_adjusted_form_advantage":"Adjusted Form (60d)",
    "strength_of_schedule_advantage":"Strength of Schedule",
    "performance_vs_expectation_advantage":"Performance vs Expectation",
}

async def active_model(session):return (await session.execute(select(WinProbabilityModelArtifact).where(WinProbabilityModelArtifact.active.is_(True)).order_by(WinProbabilityModelArtifact.trained_at.desc()))).scalars().first()


def quality_gate_passed(metrics:dict)->bool:
    test=metrics.get("metrics",{}).get("test",{})
    baseline_rows=[value for value in metrics.get("baselines",{}).values() if isinstance(value,dict)]
    best_log=min((float(value["log_loss"]) for value in baseline_rows if value.get("log_loss") is not None),default=float("inf"))
    best_brier=min((float(value["brier_score"]) for value in baseline_rows if value.get("brier_score") is not None),default=float("inf"))
    # Preserve the existing gate: improving either proper scoring rule is enough.
    return float(test.get("log_loss",float("inf"))) < best_log or float(test.get("brier_score",float("inf"))) < best_brier


def _feature_vector(matchup:dict,format:str,ranking_advantage:float=0.0)->dict[str,float]:
    factors={item["key"]:item for item in matchup.get("factors",[])}
    def centered(key:str)->float:
        # Reliability-weighted, matching matchup_engine.calculate_matchup's own per-factor
        # discounting: a sparse-data factor (e.g. tactical_matchup) that the matchup score
        # itself is already discounting toward zero must reach the model at the same reduced
        # strength, not at full weight -- otherwise ML and matchup disagree on how much a
        # low-confidence factor should matter. Must match AnalyticsAsOfService.features'
        # centered() exactly (an is-None check, not `or 50`: a legitimate score of 0 is
        # falsy and would otherwise be misread as "missing" and rounded up to neutral).
        factor=factors.get(key) or {}
        score=factor.get("score")
        if score is None:return 0.0
        reliability=max(0.,min(1.,float(factor.get("confidence") or 0.0)))
        return (float(score)-50.0)/50.0*reliability
    strength=centered("team_strength")
    form=matchup.get("form_context",{})
    form_a=form.get("team_a_form_context",{});form_b=form.get("team_b_form_context",{})
    def form_delta(key:str)->float:
        a,b=form_a.get(key),form_b.get(key)
        return 0.0 if a is None or b is None else (float(a)-float(b))/100.0
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
        "tournament_form_advantage":form_delta("tournament_form_score"),
        "recent_60d_adjusted_form_advantage":form_delta("recent_60d_adjusted_form_score"),
        "strength_of_schedule_advantage":form_delta("strength_of_schedule_score"),
        "performance_vs_expectation_advantage":form_delta("performance_vs_expectation_score"),
    }
    return {key:float(values[key]) for key in WIN_PROBABILITY_FEATURES}

def _distribution(values):
    a=np.asarray(values,float);return {"min":float(a.min()),"p10":float(np.percentile(a,10)),"p25":float(np.percentile(a,25)),"median":float(np.median(a)),"p75":float(np.percentile(a,75)),"p90":float(np.percentile(a,90)),"max":float(a.max())} if len(a) else {}

def explain_prediction(model:WinProbabilityModel,features:dict[str,float],probability:float)->dict:
    keys=list(model.artifact["features"])
    neutral={key:0.0 for key in keys}
    neutral_probability=model.predict_symmetric([neutral])[0]
    coefficients=dict(zip(keys,model.artifact.get("coefficients",[])))
    impacts=[]
    for key in keys:
        without=dict(features);without[key]=0.0
        without_probability=model.predict_symmetric([without])[0]
        impact=(probability-without_probability)*100
        impacts.append({"key":key,"label":FEATURE_LABELS.get(key,key.replace("_"," ").title()),
            "feature_value":round(float(features.get(key,0)),6),"coefficient":round(float(coefficients.get(key,0)),6),
            "impact_percentage_points":round(impact,3),"favors":"team_a" if impact>.005 else "team_b" if impact<-.005 else "neutral",
            "counterintuitive":float(features.get(key,0))*impact < -.00001})
    impacts.sort(key=lambda item:abs(item["impact_percentage_points"]),reverse=True)
    return {"method":"leave_one_feature_at_neutral","neutral_probability":neutral_probability,
        "predicted_probability":probability,"top_factors":impacts,
        "has_counterintuitive_factors":any(item["counterintuitive"] and abs(item["impact_percentage_points"])>=.5 for item in impacts),
        "note":"Локальная модельная атрибуция: изменение вероятности при нейтрализации одного признака; не является причинной оценкой."}

async def train_win_probability(session:AsyncSession,mode:str="pre_veto",feature_schema_version:str=WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3,dataset:tuple[list,dict]|None=None)->dict:
    if feature_schema_version!=WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3:raise ValueError(f"Unknown feature_schema_version: {feature_schema_version}")
    feature_names=WIN_PROBABILITY_FEATURES_V3
    # dataset lets a caller that also needs the raw rows (e.g. for feature diagnostics right
    # after training) pass an already-built build_dataset_v3() result instead of paying for
    # a second full build -- that pipeline has no bulk preload and re-running it is expensive.
    rows,report=dataset if dataset is not None else await AnalyticsAsOfService(session).build_dataset_v3(mode)
    train,validation,test=temporal_split(rows)
    if not test or not validation:raise ValueError("Insufficient chronological series for train/validation/test.")
    model=WinProbabilityModel.train([x.features for x in train],[x.target for x in train],feature_names=feature_names,feature_schema_version=feature_schema_version);metrics={"train":probability_metrics(model.predict_symmetric([x.features for x in train]),[x.target for x in train]),"validation":probability_metrics(model.predict_symmetric([x.features for x in validation]),[x.target for x in validation]),"test":probability_metrics(model.predict_symmetric([x.features for x in test]),[x.target for x in test])}
    def baseline(name,pred):return {name:probability_metrics(pred,[x.target for x in test])}
    baselines={**baseline("neutral_50",[.5]*len(test))}
    for name,key in (("team_strength","team_strength_difference"),("matchup_score","matchup_score_centered")):
        # Always a genuine single-feature model on `key`, independent of the candidate's
        # feature_names -- if key isn't among feature_names (e.g. team_strength_difference
        # after the v3 forward-selection restart), the old code built every row as all-zeros,
        # silently degenerating this baseline into a copy of neutral_50 instead of measuring
        # the real single-factor floor the candidate needs to beat.
        bm=WinProbabilityModel.train([{key:x.features[key]} for x in train],[x.target for x in train],feature_names=[key]);baselines.update(baseline(name,bm.predict_symmetric([{key:x.features[key]} for x in test])))
    predictions=model.predict_symmetric([x.features for x in test]);metadata={"split":{"strategy":"70_15_15_chronological","training_series":len(train),"validation_series":len(validation),"test_series":len(test),"train_dates":[train[0].match_date.isoformat(),train[-1].match_date.isoformat()],"validation_dates":[validation[0].match_date.isoformat(),validation[-1].match_date.isoformat()],"test_dates":[test[0].match_date.isoformat(),test[-1].match_date.isoformat()]},"metrics":metrics,"baselines":baselines,"probability_distribution":_distribution(predictions),"extremes":{"below_20":sum(p<.2 for p in predictions),"above_80":sum(p>.8 for p in predictions)},"coefficients":dict(zip(feature_names,model.artifact["coefficients"])),"coverage":report,"calibration_method":"raw_logistic","strict_historical":True}
    ordinal=int((await session.scalar(select(func.max(WinProbabilityModelArtifact.id)))) or 0)+1
    model_version=f"v{ordinal}"
    artifact={**model.artifact,"model_version":model_version}
    passed=quality_gate_passed(metadata)
    row=WinProbabilityModelArtifact(model_version=model_version,feature_schema_version=feature_schema_version,trained_at=datetime.now(UTC),training_series=len(train),validation_series=len(validation),test_series=len(test),artifact=artifact,metrics=metadata,dataset_report=report,trained=True,quality_gate_passed=passed,active=False,forced_active=False);session.add(row);await session.flush();return {"artifact_id":row.id,"model_version":model_version,"trained":True,"quality_gate_passed":passed,"active":False,"forced_active":False,"activated":False,**metadata}

async def activate_win_probability(session:AsyncSession,artifact_id:int,force:bool=False)->dict:
    row=await session.get(WinProbabilityModelArtifact,artifact_id)
    if not row:raise ValueError("Model artifact not found.")
    if row.artifact.get("sandbox"):
        raise ValueError("Sandbox candidates cannot be activated.")
    passed=bool(row.quality_gate_passed)
    if not passed and not force:
        raise ValueError("Candidate does not outperform the best baseline on Log Loss or Brier; activation rejected.")
    await session.execute(update(WinProbabilityModelArtifact).values(active=False,forced_active=False))
    row.active=True;row.forced_active=not passed
    await session.flush()
    return {"artifact_id":row.id,"model_version":row.model_version,"trained":row.trained,"quality_gate_passed":passed,"active":True,"forced_active":row.forced_active,"model_status":"experimental" if row.forced_active else "active"}

async def predict_win_probability(session:AsyncSession,a:int,b:int,format:str="bo3",mode:str="pre_veto",as_of:date|None=None,series_id:int|None=None)->dict:
    artifact=await active_model(session)
    if not artifact:return {"prediction_status":"model_not_trained","model_version":None,"model_status":"unavailable","quality_gate_passed":False,"team_a":{"id":a,"probability":None},"team_b":{"id":b,"probability":None},"confidence":0,"limitations":[]}
    cutoff=as_of or date.today();historical=cutoff<date.today()
    # Always go through MatchupService.calculate: it already resolves ACTIVE_MATCHUP_CONFIG
    # for both the historical and live branches internally. Calling AnalyticsAsOfService
    # directly here (as before) skipped that resolution and always used matchup_v1 for
    # historical predictions, regardless of which matchup engine was actually active.
    matchup=await MatchupService(session).calculate(a,b,format,mode,cutoff,series_id)
    if historical:
        features=matchup.get("prediction_features") or _feature_vector(matchup,format)
    else:
        teams=list((await session.execute(select(Team).where(Team.id.in_((a,b))))).scalars())
        indexed={team.id:team for team in teams};rank_a=indexed.get(a).current_rank if indexed.get(a) else None;rank_b=indexed.get(b).current_rank if indexed.get(b) else None
        rank_advantage=0.0 if rank_a is None or rank_b is None else max(-30,min(30,rank_b-rank_a))/30
        features=_feature_vector(matchup,format,rank_advantage)
    confidence=matchup.get("reliability",0);status="insufficient_data" if confidence<MIN_PREDICTION_CONFIDENCE else "available";model=WinProbabilityModel(artifact.artifact);p=model.predict_symmetric([features])[0] if status=="available" else None
    explanation=explain_prediction(model,features,p) if p is not None else None
    return {"model_version":artifact.model_version,"feature_schema_version":artifact.feature_schema_version,"trained_at":artifact.trained_at,"model_status":"experimental" if artifact.forced_active else "active","quality_gate_passed":artifact.quality_gate_passed,"prediction_status":status,"team_a":{"id":a,"name":matchup.get("team_a",{}).get("name"),"probability":p},"team_b":{"id":b,"name":matchup.get("team_b",{}).get("name"),"probability":None if p is None else 1-p},"confidence":confidence,"basis":{"analysis_mode":mode,"veto":"actual_veto" if mode=="post_veto" else "calculated_veto","matchup_score":matchup["team_a"]["score"]},"features":features,"explanation":explanation,"matchup":matchup,"limitations":matchup.get("limitations",[])}

async def save_prediction(session:AsyncSession,**kwargs)->dict:
    result=await predict_win_probability(session,**kwargs)
    if result["prediction_status"]!="available":return result
    row=MatchPrediction(series_id=kwargs.get("series_id"),as_of=kwargs.get("as_of") or date.today(),mode=kwargs.get("mode","pre_veto"),source="live_saved_prediction",model_version=result["model_version"],feature_schema_version=result["feature_schema_version"],team_a_id=kwargs["a"],team_b_id=kwargs["b"],team_a_probability=Decimal(str(result["team_a"]["probability"])),team_b_probability=Decimal(str(result["team_b"]["probability"])),confidence=Decimal(str(result["confidence"])),feature_snapshot={"features":result["features"],"basis":result["basis"]},prediction_status="available");session.add(row);await session.flush();return {**result,"prediction_id":row.id}


async def backtest_win_probability(session:AsyncSession,mode:str="pre_veto",artifact_id:int|None=None)->dict:
    artifact=await session.get(WinProbabilityModelArtifact,artifact_id) if artifact_id else await active_model(session)
    if artifact is None:raise ValueError("No active Win Probability model.")
    rows,coverage=await AnalyticsAsOfService(session).build_dataset_v3(mode);_,_,test=temporal_split(rows)
    model=WinProbabilityModel(artifact.artifact);probabilities=model.predict_symmetric([item.features for item in test])
    return {"model_version":artifact.model_version,"feature_schema_version":artifact.feature_schema_version,"analysis_mode":mode,"test_series":len(test),"metrics":probability_metrics(probabilities,[item.target for item in test]),"coverage":coverage,"probability_distribution":_distribution(probabilities)}


async def win_probability_status(session:AsyncSession)->dict:
    active=await active_model(session)
    rows=list((await session.execute(select(WinProbabilityModelArtifact).order_by(WinProbabilityModelArtifact.trained_at.desc()))).scalars())
    def payload(row):
        return {"id":row.id,"model_version":row.model_version,"feature_schema_version":row.feature_schema_version,"trained_at":row.trained_at,"trained":row.trained,"quality_gate_passed":row.quality_gate_passed,"active":row.active,"forced_active":row.forced_active,"model_status":"experimental" if row.forced_active else "active" if row.active else "inactive","training_series":row.training_series,"validation_series":row.validation_series,"test_series":row.test_series,"eligible_series":row.training_series+row.validation_series+row.test_series,"metrics":row.metrics.get("metrics",{}).get("test",{}),"baselines":row.metrics.get("baselines",{})}
    return {"active":None if active is None else payload(active),"artifacts":[payload(row) for row in rows]}
