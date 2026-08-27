import {useCallback,useEffect,useState} from "react";
import {activateMLModel,getMLModels,trainMLModel} from "../api";
import type {MLModelArtifact,MLModelsStatus} from "../types";

const metric=(value:number|undefined)=>value===undefined?"—":value.toFixed(5);
const baseline=(model:MLModelArtifact,key:"brier_score"|"log_loss")=>{
  const values=Object.values(model.baselines).map(item=>item[key]).filter((value):value is number=>value!==undefined);
  return values.length?Math.min(...values):undefined;
};

export function MLModelsPage(){
  const [data,setData]=useState<MLModelsStatus|null>(null);const [error,setError]=useState<string|null>(null);const [busy,setBusy]=useState(false);
  const load=useCallback(()=>getMLModels().then(setData).catch((e:unknown)=>setError(e instanceof Error?e.message:"Не удалось загрузить модели.")),[]);
  useEffect(()=>{void load()},[load]);
  const activate=async(model:MLModelArtifact)=>{const force=!model.quality_gate_passed;if(force&&!window.confirm("Модель не прошла quality gate. Активировать её экспериментально?"))return;setBusy(true);setError(null);try{await activateMLModel(model.id,force);await load()}catch(e){setError(e instanceof Error?e.message:"Не удалось активировать модель.")}finally{setBusy(false)}};
  const train=async()=>{setBusy(true);setError(null);try{await trainMLModel();await load()}catch(e){setError(e instanceof Error?e.message:"Не удалось обучить модель.")}finally{setBusy(false)}};
  return <main className="page"><nav className="page-links"><a className="back-link" href="/">← На главную</a></nav><header className="section-heading"><div><p className="eyebrow">ML administration</p><h1>Prediction models</h1><p>Каждый retrain строит новую версию с нуля на полном актуальном temporal dataset.</p></div><button className="button button--primary" disabled={busy} onClick={()=>void train()}>{busy?"Выполняется…":"Обучить новую версию"}</button></header>{error&&<div className="empty-state empty-state--error">{error}</div>}{!data&&!error&&<div className="empty-state">Загружаю модели…</div>}<section className="team-grid">{data?.artifacts.map(model=><article className="team-card" key={model.id}><header className="team-card__header"><div><p className="eyebrow">Model {model.model_version}</p><h2>Eligible series: {model.eligible_series}</h2></div><span className="source-badge">{model.active?(model.forced_active?"ACTIVE / EXPERIMENTAL":"ACTIVE"):"INACTIVE"}</span></header><div className="team-card__stats"><span><small>Brier</small><strong>{metric(model.metrics.brier_score)}</strong></span><span><small>Baseline Brier</small><strong>{metric(baseline(model,"brier_score"))}</strong></span><span><small>Log Loss</small><strong>{metric(model.metrics.log_loss)}</strong></span><span><small>Baseline Log Loss</small><strong>{metric(baseline(model,"log_loss"))}</strong></span></div><p><b>Quality Gate: {model.quality_gate_passed?"PASSED":"FAILED"}</b></p><p className="formula">Train {model.training_series} · Validation {model.validation_series} · Test {model.test_series} · {new Date(model.trained_at).toLocaleString("ru-RU")}</p>{model.forced_active&&<div className="empty-state"><b>Экспериментальная ML-модель</b><br/>Модель активирована вручную и пока не прошла проверку качества.</div>}{!model.active&&<button className="button button--primary" disabled={busy} onClick={()=>void activate(model)}>{model.quality_gate_passed?"Активировать":"Активировать экспериментально"}</button>}</article>)}</section></main>
}
