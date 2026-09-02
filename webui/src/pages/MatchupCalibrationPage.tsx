import {useEffect,useState} from "react";
import {getMatchupCalibration} from "../api";
import type {MatchupCalibrationModelReport,MatchupCalibrationReport} from "../types";

const pct=(x:number|null)=>x==null?"—":`${(x*100).toFixed(1)}%`;
function ModelCard({title,value}:{title:string;value:MatchupCalibrationModelReport}){return <article><span>{title}</span><strong>{value.version}</strong><b>Accuracy {pct(value.accuracy)}</b><small>Predictions {value.predictions}/{value.matches} · Coverage {pct(value.coverage)}</small><small>Abstentions {value.abstentions}</small></article>}

export function MatchupCalibrationPage(){
 const [data,setData]=useState<MatchupCalibrationReport|null>(null),[error,setError]=useState("");
 useEffect(()=>{getMatchupCalibration().then(setData).catch(x=>setError(x instanceof Error?x.message:"Ошибка calibration"))},[]);
 if(error)return <main className="page"><div className="empty-state empty-state--error">{error}</div></main>;
 if(!data)return <main className="page"><div className="empty-state">Считаю temporal-safe calibration…</div></main>;
 const changes=data.abstention_changes??{lost_predictions:0,lost_correct_predictions:0,avoided_baseline_errors:0,new_predictions:0,new_correct_predictions:0,new_incorrect_predictions:0};
 return <main className="page">
  <nav className="page-links"><a href="/">← Главная</a><a href="/model-sandbox">Ручные эксперименты →</a><a href="/prediction-history">Prediction History →</a></nav>
  <header className="compare-heading"><p className="eyebrow">Read-only проверка готовых версий</p><h1>Matchup Calibration — V1 против V2</h1><p>Сравнивает два уже заданных в коде versioned-конфига на temporal-safe истории. Для своих весов и reliability используйте Model Sandbox.</p><p>Gate: <strong>{data.gate_status}</strong> · temporal-safe sample {data.sample_size}</p></header>
  <section className="prediction-history__stats"><ModelCard title="Baseline" value={data.baseline}/><ModelCard title="Candidate" value={data.candidate}/><article><span>Accuracy delta</span><strong>{data.delta.accuracy==null?"—":`${data.delta.accuracy>=0?"+":""}${(data.delta.accuracy*100).toFixed(1)} pp`}</strong></article><article><span>Real winner flips</span><strong>{data.flips.total}</strong><b>Fixed {data.flips.v2_fixed_v1_error} · Broken {data.flips.v2_broke_v1_correct} · Net {data.flips.net_improvement}</b></article></section>
  <section className="prediction-conflict__stats"><article><strong>V1 prediction → 50/50</strong><span>{changes.lost_predictions}</span><small>Потеряно правильных: {changes.lost_correct_predictions}</small><small>Избежали ошибок v1: {changes.avoided_baseline_errors}</small></article><article><strong>50/50 → V2 prediction</strong><span>{changes.new_predictions}</span><small>Правильных новых: {changes.new_correct_predictions}</small><small>Ошибочных новых: {changes.new_incorrect_predictions}</small></article></section>
  <section className="prediction-calibration"><h2>Factor impact comparison</h2><table><thead><tr><th>Factor</th><th>V1 avg impact</th><th>V2 avg impact</th></tr></thead><tbody>{Object.entries(data.factor_impact_comparison).map(([factor,x])=><tr key={factor}><td>{factor}</td><td>{x.baseline_average_absolute_contribution?.toFixed(2)??"—"}</td><td>{x.candidate_average_absolute_contribution?.toFixed(2)??"—"}</td></tr>)}</tbody></table></section>
  <section className="prediction-calibration"><h2>Real flipped matches</h2><table><thead><tr><th>Match</th><th>V1 score A</th><th>V2 score A</th><th>Result</th><th>Main changes</th></tr></thead><tbody>{data.flips.matches.map(x=><tr key={x.match_id}><td><a href={`/matches/${x.match_id}`}>{x.match}</a></td><td>{x.baseline_score.toFixed(1)}</td><td>{x.candidate_score.toFixed(1)}</td><td>{x.result?.toUpperCase()}</td><td>{x.main_changed_factors.map(f=>`${f.factor}: ${f.baseline_contribution.toFixed(1)} → ${f.candidate_contribution.toFixed(1)}`).join("; ")}</td></tr>)}</tbody></table></section>
 </main>;
}
