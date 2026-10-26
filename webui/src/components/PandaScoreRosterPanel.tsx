import {useEffect, useState} from "react";
import {getPandaScoreRoster, refreshPandaScoreRoster, selectPandaScoreRoster} from "../api";
import type {PandaScoreRosterSnapshot} from "../api";

export function PandaScoreRosterPanel({teamId, onSaved}: {teamId:number;onSaved:()=>Promise<void>}) {
  const [snapshot,setSnapshot]=useState<PandaScoreRosterSnapshot|null>(null);
  const [selected,setSelected]=useState<number[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  function show(value:PandaScoreRosterSnapshot|null){setSnapshot(value);setSelected(value?.selected_ids.filter(id=>value.players.some(p=>p.id===id))??[]);}
  useEffect(()=>{let active=true;void getPandaScoreRoster(teamId).then(value=>{if(active)show(value);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[teamId]);
  async function run(action:()=>Promise<PandaScoreRosterSnapshot>){setBusy(true);setError("");try{const value=await action();show(value);if(value.status==="saved")await onSaved();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <section className="strength-panel">
    <h2>Основной состав · PandaScore</h2>
    <p>Если источник возвращает ровно пять игроков, состав сохраняется автоматически. При большем списке выберите основную пятёрку.</p>
    <button className="button" disabled={busy} onClick={()=>void run(()=>refreshPandaScoreRoster(teamId))}>{busy?"Обновляю…":"Получить состав из PandaScore"}</button>
    {snapshot&&<>
      <p>Получено: {new Date(snapshot.checked_at).toLocaleString("ru-RU")} · {snapshot.players.length} игроков</p>
      {snapshot.status==="saved"?<p role="status">Основная пятёрка сохранена: {snapshot.players.filter(p=>selected.includes(p.id)).map(p=>p.name).join(" / ")}</p>:<p role="status">{snapshot.status==="partial"?"Источник вернул неполный состав. Предыдущая основа сохранена.":"Выберите ровно пять игроков. Источник не указывает, кто из остальных запасной."}</p>}
      <div className="drawer-grid">{snapshot.players.map(p=><label key={p.id}><input type="checkbox" disabled={busy||snapshot.status==="partial"} checked={selected.includes(p.id)} onChange={e=>setSelected(e.target.checked?[...selected,p.id]:selected.filter(id=>id!==p.id))}/>{p.name} · {p.nationality??"—"} · #{p.id}</label>)}</div>
      <button className="button" disabled={busy||selected.length!==5||snapshot.status==="partial"} onClick={()=>void run(()=>selectPandaScoreRoster(teamId,selected))}>Сохранить основную пятёрку ({selected.length}/5)</button>
    </>}
    {error&&<p role="alert" className="notice notice--error">{error}</p>}
  </section>;
}
