from __future__ import annotations
from dataclasses import dataclass
from math import exp,log
from typing import Sequence
import numpy as np
from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURES,WIN_PROBABILITY_FEATURE_SCHEMA_VERSION,WIN_PROBABILITY_MODEL_VERSION

def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-35,35)))

def probability_metrics(probabilities:Sequence[float],targets:Sequence[int])->dict:
    if not probabilities or len(probabilities)!=len(targets):raise ValueError("non-empty equal arrays required")
    p=np.asarray(probabilities,float);y=np.asarray(targets,float);eps=1e-12
    brier=float(np.mean((p-y)**2));loss=float(-np.mean(y*np.log(np.clip(p,eps,1))+ (1-y)*np.log(np.clip(1-p,eps,1))))
    bins=[];ece=0
    for low,high in ((0,.2),(.2,.3),(.3,.4),(.4,.45),(.45,.5),(.5,.55),(.55,.6),(.6,.7),(.7,.8),(.8,1.000001)):
        mask=(p>=low)&(p<high)
        if mask.any():
            predicted=float(p[mask].mean());actual=float(y[mask].mean());count=int(mask.sum());ece+=count/len(p)*abs(predicted-actual);bins.append({"low":low,"high":min(high,1),"predicted":predicted,"actual":actual,"count":count})
    pos=p[y==1];neg=p[y==0];auc=float(((pos[:,None]>neg).sum()+.5*(pos[:,None]==neg).sum())/(len(pos)*len(neg))) if len(pos) and len(neg) else None
    return {"brier_score":brier,"log_loss":loss,"ece":ece,"roc_auc":auc,"accuracy":float(np.mean((p>=.5)==y)),"calibration_bins":bins}

@dataclass
class WinProbabilityModel:
    artifact:dict
    @classmethod
    def train(cls,features:list[dict[str,float]],targets:list[int],epochs:int=600,lr:float=.08,l2:float=.03,feature_names:list[str]|None=None,feature_schema_version:str|None=None):
        if len(features)<10:raise ValueError("At least 10 historical series are required.")
        names=feature_names or WIN_PROBABILITY_FEATURES
        if not names:raise ValueError("At least one feature is required.")
        x=np.asarray([[row[key] for key in names] for row in features],float);y=np.asarray(targets,float);means=x.mean(0);scales=x.std(0);scales[scales<1e-8]=1;x=(x-means)/scales;weights=np.zeros(x.shape[1]);intercept=log((y.sum()+1)/(len(y)-y.sum()+1))
        for _ in range(epochs):
            pred=sigmoid(intercept+x@weights);error=pred-y;intercept-=lr*float(error.mean());weights-=lr*((x.T@error)/len(y)+l2*weights)
        artifact={"model_type":"standardized_logistic_regression","model_version":WIN_PROBABILITY_MODEL_VERSION,"feature_schema_version":feature_schema_version or WIN_PROBABILITY_FEATURE_SCHEMA_VERSION,"features":list(names),"means":means.tolist(),"scales":scales.tolist(),"coefficients":weights.tolist(),"intercept":intercept,"l2":l2}
        return cls(artifact)
    def predict(self,features:list[dict[str,float]])->list[float]:
        if not features:return []
        x=np.asarray([[row[key] for key in self.artifact["features"]] for row in features],float);x=(x-np.asarray(self.artifact["means"]))/np.asarray(self.artifact["scales"]);return sigmoid(self.artifact["intercept"]+x@np.asarray(self.artifact["coefficients"])).tolist()

    def predict_symmetric(
        self,
        features: list[dict[str, float]],
    ) -> list[float]:
        """Average both team orientations so P(A,B) == 1 - P(B,A)."""
        direct = self.predict(features)
        reversed_rows = [
            {key: -float(value) for key, value in row.items()}
            for row in features
        ]
        reverse = self.predict(reversed_rows)
        return [
            (probability + (1.0 - reversed_probability)) / 2.0
            for probability, reversed_probability in zip(
                direct,
                reverse,
                strict=True,
            )
        ]

def temporal_split(rows):
    ordered=sorted(rows,key=lambda x:(x.match_date,x.series_id));n=len(ordered)
    if n < 20:
        raise ValueError("At least 20 chronological series are required.")
    a=max(1,int(n*.7));b=max(a+1,int(n*.85));return ordered[:a],ordered[a:b],ordered[b:]

def fit_single_feature(train,key):
    features=[{name:(row.features[key] if name==key else 0.0) for name in WIN_PROBABILITY_FEATURES} for row in train]
    return WinProbabilityModel.train(features,[row.target for row in train]),features
