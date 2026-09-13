from __future__ import annotations

from datetime import UTC, date, datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG, MATCHUP_CONFIGS, MATCHUP_V2_CONFIG, MATCHUP_V3_CONFIG, FactorConfig, MatchupModelConfig
from cs2eye.analytics.matchup_engine import apply_config_to_payload
from cs2eye.analytics.win_probability import WinProbabilityModel, probability_metrics, temporal_split
from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURES, WIN_PROBABILITY_FEATURE_REGISTRY
from cs2eye.models.match import Match
from cs2eye.models.prediction import WinProbabilityModelArtifact
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.matchup_calibration_evaluator import MatchupCalibrationEvaluator
from cs2eye.services.matchup_service import MatchupService
from cs2eye.services.win_probability_feature_diagnostics_service import diagnose_feature_matrix
from cs2eye.services.win_probability_service import active_model, quality_gate_passed


FACTOR_LABELS={"map_veto":"Veto / Map Pool","team_strength":"Team Strength","form_context":"Tournament Form","current_roster_form":"Current Roster / Form","tactical_matchup":"Tactical","h2h":"H2H","leadership_context":"Leadership"}
FACTOR_HINTS={"map_veto":"Преимущество по ожидаемым картам, map pool и veto.","team_strength":"Общая внутренняя сила команд по текущей scoring-модели.","form_context":"Турнирная форма и recent form.","current_roster_form":"Форма текущего состава.","tactical_matchup":"Тактические и раундовые показатели из demo analytics.","h2h":"История встреч организаций и текущих составов.","leadership_context":"Сигнал капитана, тренера и leadership-компонент."}


def sandbox_config(raw:dict)->tuple[MatchupModelConfig,dict]:
    # "version" here means the template a sandbox edit starts from (as returned by
    # bootstrap()'s *_config payloads), not the resulting sandbox config's own version.
    base_version=raw.get("version") or ACTIVE_MATCHUP_CONFIG.version
    base=MATCHUP_CONFIGS.get(base_version)
    if base is None:raise ValueError(f"Unknown base matchup config version: {base_version}")
    unknown=set(raw.get("factors",{}))-set(base.factors)
    if unknown:raise ValueError(f"Unknown matchup factors: {', '.join(sorted(unknown))}")
    normalize=bool(raw.get("normalize_weights",True));items={};raw_weights={}
    for key,production in base.factors.items():
        value=raw.get("factors",{}).get(key,{})
        weight=float(value.get("weight",production.weight));minimum=float(value.get("min_reliability",production.min_reliability));maximum=float(value.get("max_effect",production.max_effect));mode=value.get("reliability_mode",production.reliability_mode)
        mode={"threshold":"thresholded"}.get(mode,mode)
        if not 0<=weight<=.5:raise ValueError(f"{key}.weight must be between 0 and 0.5.")
        if not 0<=minimum<=1:raise ValueError(f"{key}.min_reliability must be between 0 and 1.")
        if not 0<=maximum<=50:raise ValueError(f"{key}.max_effect must be between 0 and 50.")
        if mode not in {"none","gated","linear","conservative","thresholded"}:raise ValueError(f"Unsupported reliability mode for {key}.")
        raw_weights[key]=weight;items[key]=FactorConfig(weight,mode,minimum,maximum)
    total=sum(raw_weights.values())
    if normalize:
        if total<=0:raise ValueError("Weight sum must be greater than zero when normalization is enabled.")
        items={key:FactorConfig(value.weight/total,value.reliability_mode,value.min_reliability,value.max_effect) for key,value in items.items()}
    config=MatchupModelConfig("matchup_sandbox",items,bool(raw.get("redistribute_missing_weight",base.redistribute_missing_weight)),raw.get("overall_mode",base.overall_mode),float(raw.get("coverage_floor",base.coverage_floor)),float(raw.get("agreement_floor",base.agreement_floor)))
    return config,{"base_version":base.version,"raw_weight_sum":total,"normalized":normalize,"raw_weights":raw_weights,"effective_weights":{k:v.weight for k,v in items.items()}}


class ModelSandboxService:
    def __init__(self,session:AsyncSession):self.session=session

    async def bootstrap(self)->dict:
        matches=list((await self.session.scalars(select(Match).where(Match.team_a_id.is_not(None),Match.team_b_id.is_not(None)).order_by(Match.match_date.desc(),Match.id.desc()).limit(100))).all())
        active=await active_model(self.session)
        return {"production_config":self._config_payload(ACTIVE_MATCHUP_CONFIG),"conservative_config":self._config_payload(MATCHUP_V2_CONFIG),"conservative_available":True,"v3_config":self._config_payload(MATCHUP_V3_CONFIG),"v3_available":True,"matches":[{"id":x.id,"match_date":x.match_date,"status":x.status,"format":x.format,"team_a_id":x.team_a_id,"team_b_id":x.team_b_id} for x in matches],"ml":{"current_schema":active.feature_schema_version if active else None,"features":[{"key":key,**WIN_PROBABILITY_FEATURE_REGISTRY[key]} for key in WIN_PROBABILITY_FEATURES]}}

    @staticmethod
    def _config_payload(config):
        return {"version":config.version,"normalize_weights":False,"redistribute_missing_weight":config.redistribute_missing_weight,"overall_mode":config.overall_mode,"coverage_floor":config.coverage_floor,"agreement_floor":config.agreement_floor,"factors":{key:{"label":FACTOR_LABELS.get(key,key),"hint":FACTOR_HINTS.get(key,""),"weight":value.weight,"reliability_mode":value.reliability_mode,"min_reliability":value.min_reliability,"max_effect":value.max_effect} for key,value in config.factors.items()}}

    async def preview(self,match_id:int,raw:dict)->dict:
        match=await self.session.get(Match,match_id)
        if not match or not match.team_a_id or not match.team_b_id:raise ValueError("Match not found or teams are unresolved.")
        mode="post_veto" if match.veto_data_status in {"complete","partial"} else "pre_veto";fmt=match.format if match.format in {"bo1","bo3","bo5"} else "bo3"
        if match.status=="completed":payload=await AnalyticsAsOfService(self.session).calculate(match.team_a_id,match.team_b_id,match.match_date,fmt,mode,match.id)
        else:payload=await MatchupService(self.session).calculate(match.team_a_id,match.team_b_id,fmt,mode,date.today(),match.id)
        config,meta=sandbox_config(raw);production=apply_config_to_payload(payload,ACTIVE_MATCHUP_CONFIG);candidate=apply_config_to_payload(payload,config)
        pf={x["key"]:x for x in production["factors"]};cf={x["key"]:x for x in candidate["factors"]}
        comparison=[]
        for key in pf.keys()|cf.keys():
            p=pf.get(key,{});c=cf.get(key,{})
            comparison.append({"key":key,"label":FACTOR_LABELS.get(key,key),"score":c.get("score"),"reliability":c.get("confidence"),"raw_contribution":None if c.get("score") is None else (float(c["score"])-50)*config.factors[key].weight,"production_contribution":float(p.get("impact") or 0),"sandbox_contribution":float(c.get("impact") or 0)})
        old=production["advantage"]["team_id"];new=candidate["advantage"]["team_id"]
        return {"production":production,"sandbox":candidate,"factor_comparison":comparison,"winner_changed":old!=new,"production_winner_id":old,"sandbox_winner_id":new,"config_meta":meta}

    async def backtest(self,raw:dict,limit:int=120)->dict:
        config,meta=sandbox_config(raw);report=await MatchupCalibrationEvaluator(self.session).evaluate(limit=limit,baseline=ACTIVE_MATCHUP_CONFIG,candidate=config);return {**report,"config_meta":meta}

    async def train_ml(self,enabled:list[str])->dict:
        if not enabled:raise ValueError("At least one feature must be enabled.")
        if len(enabled)!=len(set(enabled)):raise ValueError("Enabled features must be unique.")
        unknown=set(enabled)-set(WIN_PROBABILITY_FEATURES)
        if unknown:raise ValueError(f"Unknown features: {', '.join(sorted(unknown))}")
        rows,coverage=await AnalyticsAsOfService(self.session).build_dataset("pre_veto");train,validation,test=temporal_split(rows)
        model=WinProbabilityModel.train([x.features for x in train],[x.target for x in train],feature_names=enabled)
        quality={part:probability_metrics(model.predict_symmetric([x.features for x in values]),[x.target for x in values]) for part,values in (("train",train),("validation",validation),("test",test))}
        current=await active_model(self.session);current_quality=None
        if current:current_quality=probability_metrics(WinProbabilityModel(current.artifact).predict_symmetric([x.features for x in test]),[x.target for x in test])
        metadata={"metrics":quality,"baselines":{"current_ml":current_quality} if current_quality else {},"coverage":coverage,"sandbox":True,"enabled_features":enabled}
        artifact={**model.artifact,"sandbox":True,"feature_schema_version":"custom_sandbox"};passed=quality_gate_passed(metadata) if current_quality else False
        ordinal=int((await self.session.scalar(select(func.max(WinProbabilityModelArtifact.id)))) or 0)+1
        row=WinProbabilityModelArtifact(model_version=f"sandbox_{ordinal}",feature_schema_version="custom_sandbox",trained_at=datetime.now(UTC),training_series=len(train),validation_series=len(validation),test_series=len(test),artifact=artifact,metrics=metadata,dataset_report=coverage,trained=True,quality_gate_passed=passed,active=False,forced_active=False);self.session.add(row);await self.session.flush()
        diagnostics=diagnose_feature_matrix([{key:x.features[key] for key in enabled} for x in train],[x.target for x in train],artifact,feature_names=enabled)
        return {"candidate_id":row.id,"model_version":row.model_version,"schema":"custom_sandbox","status":"sandbox","active":False,"enabled_features":enabled,"quality":{"current":current_quality,"sandbox":quality["test"]},"diagnostics":diagnostics,"gate_preview":"PASS" if passed else "FAIL"}
