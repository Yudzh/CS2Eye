from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from itertools import combinations
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.win_probability import WinProbabilityModel, probability_metrics, temporal_split
from cs2eye.analytics.win_probability_config import (
    FEATURE_DIAGNOSTICS_BOOTSTRAP_RUNS, FEATURE_DIAGNOSTICS_HIGH_CORRELATION,
    FEATURE_DIAGNOSTICS_MIN_SAMPLES, FEATURE_DIAGNOSTICS_MODERATE_SIGN_RATE,
    FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD, FEATURE_DIAGNOSTICS_SEED,
    FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE, FEATURE_DIAGNOSTICS_VERY_HIGH_CORRELATION,
    WIN_PROBABILITY_FEATURE_REGISTRY, WIN_PROBABILITY_FEATURES,
)
from cs2eye.models.prediction import MLFeatureDiagnosticRun, WinProbabilityModelArtifact
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.win_probability_service import active_model


def _sign(value: float, tolerance: float = 1e-10) -> str:
    return "positive" if value > tolerance else "negative" if value < -tolerance else "zero"


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2 or np.std(a) < FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD or np.std(b) < FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD:
        return None
    value = float(np.corrcoef(a, b)[0, 1])
    return value if np.isfinite(value) else None


def _single_feature_coefficient(values: np.ndarray, targets: np.ndarray) -> float | None:
    if len(values) < 10 or np.std(values) < FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD or len(np.unique(targets)) < 2:
        return None
    # Same standardized logistic optimizer and regularization as production.
    rows = [{key: (float(value) if key == WIN_PROBABILITY_FEATURES[0] else 0.0)
             for key in WIN_PROBABILITY_FEATURES} for value in values]
    model = WinProbabilityModel.train(rows, targets.astype(int).tolist())
    return float(model.artifact["coefficients"][0])


def _vif(matrix: np.ndarray, index: int) -> tuple[float | None, str]:
    y = matrix[:, index]
    if np.std(y) < FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD:
        return None, "singular"
    x = np.delete(matrix, index, axis=1)
    # Constant neighbours contain no collinearity information and would make
    # the design matrix singular for every otherwise valid feature.
    x = x[:,np.std(x,axis=0)>=FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD]
    x = np.column_stack((np.ones(len(x)), x))
    try:
        coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
        if rank < x.shape[1]:
            return None, "singular"
        residual = y - x @ coefficients
        denominator = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - float(np.sum(residual ** 2)) / denominator
        if r2 >= 1 - 1e-10:
            return None, "singular"
        value = max(1.0, 1 / (1 - r2))
        return value, "high" if value > 10 else "elevated" if value >= 5 else "normal"
    except np.linalg.LinAlgError:
        return None, "singular"


def _clusters(correlations: np.ndarray) -> list[dict[str, Any]]:
    edges = {i: set() for i in range(len(WIN_PROBABILITY_FEATURES))}
    for left, right in combinations(range(len(WIN_PROBABILITY_FEATURES)), 2):
        value = correlations[left, right]
        if np.isfinite(value) and abs(value) >= FEATURE_DIAGNOSTICS_HIGH_CORRELATION:
            edges[left].add(right); edges[right].add(left)
    groups=[];seen=set()
    for start in edges:
        if start in seen or not edges[start]: continue
        stack=[start];component=set()
        while stack:
            node=stack.pop()
            if node in component: continue
            component.add(node);stack.extend(edges[node])
        seen.update(component)
        groups.append({"group": f"cluster_{len(groups)+1}", "features": [WIN_PROBABILITY_FEATURES[i] for i in sorted(component)]})
    return groups


def diagnose_feature_matrix(
    feature_rows: list[dict[str, float]], targets: list[int], artifact: dict,
    *, bootstrap_runs: int = FEATURE_DIAGNOSTICS_BOOTSTRAP_RUNS,
    seed: int = FEATURE_DIAGNOSTICS_SEED,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    names=feature_names or WIN_PROBABILITY_FEATURES
    matrix=np.asarray([[row[key] for key in names] for row in feature_rows], float)
    y=np.asarray(targets, float);sample_size=len(y)
    with np.errstate(divide="ignore",invalid="ignore"):
        correlations=np.atleast_2d(np.corrcoef(matrix, rowvar=False)) if sample_size > 1 else np.full((len(names),)*2, np.nan)
    coefficients=dict(zip(artifact["features"], artifact["coefficients"], strict=True))
    rng=np.random.default_rng(seed);boot=defaultdict(list)
    if sample_size >= 10 and len(np.unique(y)) == 2:
        for _ in range(bootstrap_runs):
            indices=rng.integers(0, sample_size, sample_size)
            if len(np.unique(y[indices])) < 2: continue
            model=WinProbabilityModel.train([feature_rows[i] for i in indices], y[indices].astype(int).tolist(),feature_names=names)
            for key,value in zip(names,model.artifact["coefficients"],strict=True):boot[key].append(float(value))
    features=[]
    for index,key in enumerate(names):
        values=matrix[:,index];meta=WIN_PROBABILITY_FEATURE_REGISTRY[key];expected=meta["expected_direction"]
        current=float(coefficients.get(key,0));target_corr=_correlation(values,y)
        # Reuse production optimizer, placing the examined values in the first slot.
        univariate=None if len(names)!=len(WIN_PROBABILITY_FEATURES) else _single_feature_coefficient(values,y)
        runs=np.asarray(boot[key],float);valid=len(runs);positive=int(np.sum(runs>1e-10));negative=int(np.sum(runs< -1e-10));zero=valid-positive-negative
        expected_count=positive if expected=="positive" else negative
        expected_rate=expected_count/valid if valid else None
        related=[]
        for other in range(len(names)):
            if other==index:continue
            value=correlations[index,other]
            if np.isfinite(value): related.append({"feature":names[other],"correlation":float(value),"level":"very_high" if abs(value)>=FEATURE_DIAGNOSTICS_VERY_HIGH_CORRELATION else "high" if abs(value)>=FEATURE_DIAGNOSTICS_HIGH_CORRELATION else "normal"})
        related.sort(key=lambda item:abs(item["correlation"]),reverse=True)
        vif,vif_status=_vif(matrix,index)
        near_constant=float(np.std(values))<FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD
        aligned_uni=univariate is not None and _sign(univariate)==expected
        aligned_corr=target_corr is not None and _sign(target_corr)==expected
        has_high=any(abs(item["correlation"])>=FEATURE_DIAGNOSTICS_HIGH_CORRELATION for item in related)
        if sample_size<FEATURE_DIAGNOSTICS_MIN_SAMPLES or near_constant or valid<max(10,bootstrap_runs//2):status="insufficient_data"
        elif expected_rate is not None and expected_rate>=FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE and _sign(current)==expected:status="stable"
        elif aligned_uni and aligned_corr and has_high and (_sign(current)!=expected or expected_rate is None or expected_rate<FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE):status="likely_multicollinearity"
        elif (univariate is not None and _sign(univariate)!=expected and target_corr is not None and _sign(target_corr)!=expected and expected_rate is not None and expected_rate<=1-FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE):status="consistent_inverse_signal"
        elif (target_corr is None or abs(target_corr)<.05) and (univariate is None or abs(univariate)<.15):status="weak_signal"
        else:status="unstable"
        stability="insufficient_data" if expected_rate is None or sample_size<FEATURE_DIAGNOSTICS_MIN_SAMPLES else "stable" if expected_rate>=FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE else "moderate" if expected_rate>=FEATURE_DIAGNOSTICS_MODERATE_SIGN_RATE else "unstable"
        features.append({"feature":key,"group":meta["group"],"expected_direction":expected,"expected_symmetry":meta["expected_symmetry"],"coefficient":current,"coefficient_sign":_sign(current),"sign_mismatch":_sign(current)!=expected,"target_correlation":target_corr,"univariate_coefficient":univariate,"mean":float(values.mean()),"std":float(values.std()),"min":float(values.min()),"max":float(values.max()),"non_zero_samples":int(np.count_nonzero(np.abs(values)>1e-12)),"unique_values":int(len(np.unique(values))),"missing_count":0,"missing_rate":0.0,"missing_note":"Temporal dataset contains post-preprocessing numeric values; unavailable inputs are represented by neutral zero.","near_constant":near_constant,"vif":vif,"vif_status":vif_status,"strongest_correlations":related[:3],"bootstrap":{"bootstrap_runs":bootstrap_runs,"valid_runs":valid,"positive_sign_runs":positive,"negative_sign_runs":negative,"zero_sign_runs":zero,"expected_sign_rate":expected_rate,"coefficient_mean":float(runs.mean()) if valid else None,"coefficient_std":float(runs.std()) if valid else None,"coefficient_p05":float(np.percentile(runs,5)) if valid else None,"coefficient_p50":float(np.percentile(runs,50)) if valid else None,"coefficient_p95":float(np.percentile(runs,95)) if valid else None},"stability_status":stability,"diagnostic_status":status})
    redundancy=[]
    for left,right in combinations(range(len(names)),2):
        value=correlations[left,right]
        if np.isfinite(value) and abs(value)>=FEATURE_DIAGNOSTICS_HIGH_CORRELATION:redundancy.append({"features":[names[left],names[right]],"correlation":float(value),"level":"very_high" if abs(value)>=FEATURE_DIAGNOSTICS_VERY_HIGH_CORRELATION else "high"})
    redundancy.sort(key=lambda item:abs(item["correlation"]),reverse=True)
    groups=[]
    for name in sorted({item["group"] for item in features}):
        items=[item for item in features if item["group"]==name]
        counts={status:sum(item["diagnostic_status"]==status for item in items) for status in ("stable","weak_signal","unstable","likely_multicollinearity","consistent_inverse_signal","insufficient_data")}
        groups.append({"group":name,"features":len(items),**counts})
    clusters=[]
    if len(names)==len(WIN_PROBABILITY_FEATURES):clusters=_clusters(correlations)
    else:
        edges={i:set() for i in range(len(names))}
        for left,right in combinations(range(len(names)),2):
            if np.isfinite(correlations[left,right]) and abs(correlations[left,right])>=FEATURE_DIAGNOSTICS_HIGH_CORRELATION:edges[left].add(right);edges[right].add(left)
        seen=set()
        for start in edges:
            if start in seen or not edges[start]:continue
            stack=[start];component=set()
            while stack:
                node=stack.pop()
                if node in component:continue
                component.add(node);stack.extend(edges[node])
            seen.update(component);clusters.append({"group":f"cluster_{len(clusters)+1}","features":[names[i] for i in sorted(component)]})
    return {"features":features,"multicollinearity_groups":clusters,"redundancy_candidates":redundancy,"groups":groups}


class WinProbabilityFeatureDiagnosticsService:
    def __init__(self,session:AsyncSession):self.session=session

    async def run(self,analysis_mode: str="pre_veto") -> dict[str,Any]:
        artifact=await active_model(self.session)
        if artifact is None:raise ValueError("No active Win Probability model.")
        rows,dataset_report=await AnalyticsAsOfService(self.session).build_dataset(analysis_mode)
        train,_,test=temporal_split(rows)
        core=diagnose_feature_matrix([row.features for row in train],[row.target for row in train],artifact.artifact)
        # Quality and ablations use the same chronological train/test boundary.
        # The active artifact is read only for its current production coefficients.
        temporal_baseline=WinProbabilityModel.train([row.features for row in train],[row.target for row in train])
        baseline=probability_metrics(temporal_baseline.predict_symmetric([row.features for row in test]),[row.target for row in test])
        ablation=[]
        for key in WIN_PROBABILITY_FEATURES:
            train_rows=[{name:(0.0 if name==key else row.features[name]) for name in WIN_PROBABILITY_FEATURES} for row in train]
            test_rows=[{name:(0.0 if name==key else row.features[name]) for name in WIN_PROBABILITY_FEATURES} for row in test]
            model=WinProbabilityModel.train(train_rows,[row.target for row in train]);quality=probability_metrics(model.predict_symmetric(test_rows),[row.target for row in test])
            ablation.append({"feature":key,"baseline_brier":baseline["brier_score"],"without_feature_brier":quality["brier_score"],"baseline_log_loss":baseline["log_loss"],"without_feature_log_loss":quality["log_loss"],"baseline_accuracy":baseline["accuracy"],"without_feature_accuracy":quality["accuracy"],"improved_without_feature":quality["brier_score"]<baseline["brier_score"] and quality["log_loss"]<baseline["log_loss"]})
        report={"model_version":artifact.model_version,"feature_schema_version":artifact.feature_schema_version,"analysis_mode":analysis_mode,"samples":len(rows),"diagnostic_train_samples":len(train),"temporal_test_samples":len(test),"quality":baseline,"dataset_report":dataset_report,**core,"ablation":ablation,"config":{"bootstrap_runs":FEATURE_DIAGNOSTICS_BOOTSTRAP_RUNS,"seed":FEATURE_DIAGNOSTICS_SEED,"minimum_samples":FEATURE_DIAGNOSTICS_MIN_SAMPLES,"high_correlation":FEATURE_DIAGNOSTICS_HIGH_CORRELATION,"very_high_correlation":FEATURE_DIAGNOSTICS_VERY_HIGH_CORRELATION,"ablation_delta_convention":"Metrics are reported directly; lower Brier/Log Loss is better."},"created_at":datetime.now(UTC).isoformat()}
        run=MLFeatureDiagnosticRun(created_at=datetime.now(UTC),model_version=artifact.model_version,feature_schema_version=artifact.feature_schema_version,sample_size=len(rows),report_json=report)
        self.session.add(run);await self.session.flush();report["id"]=run.id
        return report

    async def latest(self) -> dict[str,Any] | None:
        row=(await self.session.execute(select(MLFeatureDiagnosticRun).order_by(MLFeatureDiagnosticRun.created_at.desc()))).scalars().first()
        return None if row is None else {**row.report_json,"id":row.id}
