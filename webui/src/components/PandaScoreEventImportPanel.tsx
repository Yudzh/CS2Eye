import {useState} from 'react';
import {searchPandaScoreEvents, importPandaScoreEvent} from '../api';
import type {PandaScoreEvent, PandaScoreEventImport} from '../api';

export function PandaScoreEventImportPanel({onImported}:{onImported:()=>Promise<void>}) {
  const [query,setQuery]=useState('');
  const [rows,setRows]=useState<PandaScoreEvent[]|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [saved,setSaved]=useState<PandaScoreEventImport|null>(null);
  async function run(action:()=>Promise<void>) {
    setBusy(true);setError(null);
    try {await action()} catch(e) {setError(e instanceof Error?e.message:'Не удалось получить турнир из PandaScore.')} finally {setBusy(false)}
  }
  return <section className="pandascore-binding" aria-label="Добавить турнир из PandaScore">
    <h2>Добавить турнир из PandaScore</h2>
    <p>Введите название. Добавим команды, опубликованные матчи, результаты и доступные связи сетки. Повторное добавление обновит турнир без дублей.</p>
    <form onSubmit={e=>{e.preventDefault();setSaved(null);void run(async()=>setRows(await searchPandaScoreEvents(query.trim())))}}>
      <label>Название турнира <input required minLength={2} maxLength={160} placeholder="IEM Beijing 2026" value={query} disabled={busy} onChange={e=>{setQuery(e.target.value);setRows(null)}}/></label>
      <button className="button" disabled={busy||query.trim().length<2}>{busy?'Загружаю…':'Найти турнир'}</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {rows?.length===0&&<p>Турниры не найдены. Попробуйте название города и год.</p>}
    {rows?.map(row=><article key={row.id} className="pandascore-binding">
      <strong>{row.name}</strong><span>{row.begin_at?.slice(0,10)??'Дата не указана'} — {row.end_at?.slice(0,10)??'Дата не указана'}</span>
      <span>Стадии: {row.stages.map(s=>s.name).join(', ')||'пока не опубликованы'}</span>
      <button className="button button--primary" disabled={busy} onClick={()=>void run(async()=>{setSaved(await importPandaScoreEvent(row.id));await onImported()})}>Добавить / обновить турнир</button>
    </article>)}
    {saved&&<div role="status"><p>Сохранён <a href={`/tournaments/${saved.id}`}>{saved.name}</a>: команд — {saved.teams}, матчей из PandaScore — {saved.matches}.</p>{saved.warnings.map(w=><p key={w}>{w}</p>)}</div>}
  </section>
}
