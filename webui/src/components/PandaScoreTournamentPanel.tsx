import {useEffect,useState} from "react";
import {getPandaScoreTournament,bindPandaScoreTournament,previewPandaScoreTournament} from "../api";

export function PandaScoreTournamentPanel({tournamentId}:{tournamentId:number}) {
  const [id,setId]=useState("");
  const [linked,setLinked]=useState<number|null>(null);
  const [event,setEvent]=useState<Record<string,unknown>|null>(null);
  const [preview,setPreview]=useState<Record<string,unknown>|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    void getPandaScoreTournament(tournamentId).then(x=>{if(active){setLinked(x.external_id);setId(x.external_id?String(x.external_id):"");setEvent(x.event);}}).catch(e=>{if(active)setError(String(e));});
    return()=>{active=false;};
  },[tournamentId]);
  async function run(action:()=>Promise<void>){setBusy(true);setError("");try{await action();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  function title(value:Record<string,unknown>){
    const league=value.league as {name?:string}|null;
    const serie=value.serie as {full_name?:string;name?:string}|null;
    return [league?.name,serie?.full_name??serie?.name,String(value.name??"")].filter(Boolean).join(" → ");
  }
  return <section className="strength-panel">
    <h3>Турнирные составы · PandaScore</h3>
    <p>Составы берутся из отдельной стадии турнира PandaScore. Ожидаемая пятёрка сохраняется отдельно от основы; ручные замены имеют приоритет.</p>
    {linked?<p>Стадия PandaScore #{linked}{event?` · ${title(event)}`:" · определена по привязанным матчам"}</p>:<>
      <form onSubmit={e=>{e.preventDefault();void run(async()=>setPreview(await previewPandaScoreTournament(Number(id))));}}>
        <label>ID стадии турнира PandaScore<input type="number" min={1} required disabled={busy} value={id} onChange={e=>{setId(e.target.value);setPreview(null);}}/></label>
        <button className="button" disabled={busy||!id}>{busy?"Проверяю…":"Найти стадию"}</button>
      </form>
      {preview&&<div className="pandascore-binding"><strong>{title(preview)}</strong><span>#{String(preview.id)}</span><button className="button" disabled={busy} onClick={()=>void run(async()=>{setEvent(await bindPandaScoreTournament(tournamentId,Number(preview.id)));setLinked(Number(preview.id));setPreview(null);})}>Выбрать эту стадию</button></div>}
    </>}
    {error&&<p role="alert">{error}</p>}
    <p>После привязки нажмите «Получить состав PandaScore» у команды. Успешная пятёрка фиксируется с датой получения и автоматически повторно не перезаписывается.</p>
  </section>;
}
