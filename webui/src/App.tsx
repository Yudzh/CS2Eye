import { MapsV3Panel, MapV3Page } from "./components/MapsV3";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getLatestRun,
  getTeams,
  getTeam,
  getTeamStrengthV3,
  getTeamFormV3,
  updatePlayerRole,
  probeTopTeams,
  refreshTopTeams,
  getPlayer,
  refreshPlayer,
  getTeamMaps,
  getTeamMapDetail,
  getTeamMatchStats,
  getTeamVeto,
  getOpponentContext,
} from "./api";
import type {
  ProbeResult,
  RankingRun,
  Team,
  TeamDetail,
  TeamParticipant,
  Player,
  TeamMapAggregate,
  TeamMapScope,
  TeamMapDetail,
  TeamMatchStats,
  TeamVetoProfile,
  LeadershipScore,
  PerformanceProfile,
} from "./types";
import { TeamComparePage } from "./pages/TeamComparePage";
import { DemosPage } from "./pages/DemosPage";
import { MatchesPage } from "./pages/MatchesPage";
import { TournamentsPage } from "./pages/TournamentsPage";
import { AddTournamentPage } from "./pages/AddTournamentPage";
import { AddTournamentMatchPage } from "./pages/AddTournamentMatchPage";
import { MLModelsPage } from "./pages/MLModelsPage";
import { MLFeatureDiagnosticsPage } from "./pages/MLFeatureDiagnosticsPage";
import { PredictionHistoryPage } from "./pages/PredictionHistoryPage";
import { MatchupCalibrationPage } from "./pages/MatchupCalibrationPage";
import { ModelSandboxPage } from "./pages/ModelSandboxPage";
import { AnalystFactorsPanel } from "./components/AnalystFactorsPanel";
import { TeamFormContextBlock } from "./components/FormContextPanel";


type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; message: string };

function LeadershipFactors({value}:{value:LeadershipScore}) { return <details><summary>Breakdown · model {value.model_version}</summary>{value.factors.map(f=><div className="factor" key={f.key}><span className={`factor__impact factor__impact--${f.impact>0?"positive":f.impact<0?"negative":"neutral"}`}>{f.impact>0?"+":""}{f.impact.toFixed(2)}</span><div><strong>{f.label}: {f.available?f.normalized_score?.toFixed(1):"нет данных"}</strong><small>Вес {(f.effective_weight*100).toFixed(1)}% · sample {f.sample_size??"—"}</small></div></div>)}</details> }

function StrengthScale({label,value,reliability}:{label:string;value:number|null|undefined;reliability?:number|null}){const safe=value==null?0:Math.max(0,Math.min(100,Number(value)));return <div className="strength-scale"><div><strong>{label}</strong><span>{value==null?"—":safe.toFixed(1)}</span></div><div className={`strength-scale__track${value==null?" strength-scale__track--empty":""}`}><i style={{left:`${safe}%`}}/></div><small>{value==null?"нет данных":reliability==null?"reliability —":`reliability ${(Number(reliability)*100).toFixed(0)}%`}</small></div>}

const performanceLabels={firepower:"Firepower",entrying:"Entrying",trading:"Trading",opening:"Opening",clutching:"Clutching",sniping:"Sniping",utility:"Utility"} as const;
const performanceHelp={firepower:"KPR, ADR и выживаемость.",entrying:"Частота и успех первых T-side контактов.",trading:"Качество разменов, а не общий объём убийств.",opening:"Качество и частота первых дуэлей.",clutching:"Реализация 1vX с весом сложности.",sniping:"AWP-составляющая; низкий балл не является штрафом для rifler.",utility:"Качество flash support и utility damage со штрафом за friendly flashes."} as const;
function PerformanceProfilePanel({profile,title}:{profile:PerformanceProfile;title:string}){const [scope,setScope]=useState<"overall"|"ct"|"t">("overall");const values=profile.scopes[scope];return <section className="strength-panel performance-profile"><div className="section-heading"><div><p className="eyebrow">{profile.model_version} · standalone V3</p><h2>{title}</h2></div><span>{profile.normalization_version}</span></div><div className="performance-tabs" role="tablist">{([['overall','Both Sides'],['ct','CT Side'],['t','T Side']] as const).map(([key,label])=><button key={key} className={scope===key?"button button--primary":"button"} onClick={()=>setScope(key)}>{label}</button>)}</div><div className="performance-profile__list">{(Object.keys(performanceLabels) as Array<keyof typeof performanceLabels>).map(key=>{const item=values[key];return <details className="performance-row" key={key}><summary title={performanceHelp[key]}><div><strong>{performanceLabels[key]}</strong><small>{performanceHelp[key]}</small></div><div className={`performance-track${item.score==null?" performance-track--empty":""}`}><i style={{width:`${item.score??0}%`}}/><b style={{left:`${item.score??0}%`}}/></div><span>{item.score==null?"—":`${item.score.toFixed(1)}/100`}</span></summary><div className="performance-breakdown"><p>Reliability: <b>{item.reliability.toFixed(0)}%</b> · sample {item.sample_size}</p>{item.unavailable_reason&&<p>{item.unavailable_reason}</p>}{item.limitation&&<p>{item.limitation}</p>}{item.breakdown.map(f=><div key={f.key}><span>{f.key.replaceAll('_',' ')}</span><span>raw {f.raw_value?.toFixed(3)??"—"}</span><b>score {f.normalized_score?.toFixed(1)??"—"}</b><small>weight {(f.effective_weight*100).toFixed(0)}%</small></div>)}</div></details>})}</div><p className="formula">Score и reliability независимы. CT/T не подменяются overall.</p></section>}

function TeamStrengthV3Panel({team}:{team:TeamDetail}){const value=team.team_strength_v3;const roster=value.components.roster_quality;const execution=value.components.team_execution;const results=value.components.results_quality;return <section className="strength-panel team-strength-v3"><div className="section-heading"><div><p className="eyebrow">{value.model_version} · baseline candidate</p><h2>Team Strength V3</h2></div><small>Legacy Team Strength V2: {team.strength.team_strength_score.toFixed(1)}</small></div><div className="player-v3-scales"><StrengthScale label="Team Strength V3" value={value.score} reliability={value.reliability/100}/><StrengthScale label="Roster Quality" value={roster.score} reliability={roster.reliability/100}/><StrengthScale label="Team Execution" value={execution.score} reliability={execution.reliability/100}/><StrengthScale label="Results Quality" value={results.score} reliability={results.reliability/100}/></div><div className="team-v3-details"><details><summary>Roster Quality breakdown</summary>{roster.players.map(player=><div className="team-v3-row" key={player.id}><b>{player.nickname}</b><span>Player {player.player_strength_v3?.toFixed(1)??"—"}</span><span>Mechanical {player.mechanical_strength?.toFixed(1)??"—"}</span><span>Supporting {player.supporting_strength?.toFixed(1)??"—"}</span></div>)}<p>Average {roster.avg_all?.toFixed(1)??"—"} · Top 2 {roster.avg_top_2?.toFixed(1)??"—"} · Bottom 2 {roster.avg_bottom_2?.toFixed(1)??"—"}</p></details><details><summary>Team Execution breakdown</summary>{Object.entries(execution.metrics).map(([key,item])=><div className="team-v3-row" key={key}><b>{key.replaceAll('_',' ')}</b><span>{item.score?.toFixed(1)??"—"}</span><span>reliability {item.reliability.toFixed(0)}%</span><span>weight {(item.weight*100).toFixed(0)}%</span></div>)}</details><details><summary>Results Quality breakdown</summary><p>Overall: {results.overall.maps} maps · {results.overall.wins}–{results.overall.losses} · adjusted {results.overall.adjusted_score?.toFixed(1)??"—"}</p>{Object.entries(results.groups).map(([key,item])=><div className="team-v3-row" key={key}><b>{{top_1_10:"Top 1–10",top_11_20:"Top 11–20",top_21_30:"Top 21–30",others:"Others",unknown:"Unknown"}[key]??key}</b><span>{item.maps} maps</span><span>{item.wins}–{item.losses}</span><span>adjusted {item.adjusted_score?.toFixed(1)??"—"}</span></div>)}<p>Historical ranking coverage {results.sample.ranking_coverage.toFixed(0)}% · current roster maps {results.sample.current_roster_maps}/{results.sample.total_maps}</p></details></div><p className="formula">45% Roster Quality + 25% Team Execution + 30% Results Quality. Form, maps, veto, H2H, Firepower и Sniping исключены.</p></section>}

function signed(value:number|null|undefined){return value==null?"—":`${value>0?"+":""}${value.toFixed(1)}`}
function FormScale({value}:{value:number|null|undefined}){const left=value==null?50:Math.max(0,Math.min(100,(value+20)*2.5));return <div className={`form-scale${value==null?" form-scale--empty":""}`}><div className="form-scale__labels"><span>−20</span><span>0</span><span>+20</span></div><div className="form-scale__track"><i className="form-scale__center"/>{value!=null&&<b style={{left:`${left}%`}}/>}</div><strong>{signed(value)}</strong></div>}
function PlayerForm({value}:{value:Player["player_form_v3"]|TeamParticipant["player_form_v3"]}){return <div className="player-form"><FormScale value={value.delta}/><small>Player Form {signed(value.delta)} · reliability {value.reliability.toFixed(0)}%</small><span>Mechanical {signed(value.mechanical_form.delta)} · Supporting {signed(value.supporting_form.delta)}</span></div>}

function FormEvents({events}:{events:TeamDetail["form_v3"]["events"]}){return <div>{events.map(event=><div className="team-v3-row" key={event.series_key}><b>vs {event.opponent??`Team ${event.opponent_id??"?"}`} {event.opponent_rank?`(#${event.opponent_rank})`:""}</b><span>{event.actual_result==="win"?"W":"L"} {event.round_score}</span><span className={event.form_contribution>=0?"positive":"negative"}>{signed(event.form_contribution)}</span><small>{event.expectation_source.replaceAll('_',' ')} · expected {(event.expected*100).toFixed(0)}%</small></div>)}</div>}

function TeamFormV3CurrentPanel({team}:{team:TeamDetail}){const value=team.form_v3;const scopes=[{key:"current",label:"Current Tournament",value:value.current_tournament},{key:"recent",label:"Previous 60 days",value:value.recent_60d}];const state=value.form_delta==null?"UNAVAILABLE":value.form_delta>=5?"GOOD FORM":value.form_delta<=-5?"POOR FORM":"NEUTRAL FORM";return <section className="strength-panel form-v3"><div className="section-heading"><div><p className="eyebrow">{value.model_version} · current roster only</p><h2>Form V3</h2></div><small>Team Strength V3 {team.team_strength_v3?.score?.toFixed(1)??"—"}</small></div><FormScale value={value.form_delta}/><div className="form-v3__summary"><span><b>{state}</b></span><span>Form Score <b>{value.form_score==null?"—":`${value.form_score.toFixed(1)}/100`}</b></span><span>Reliability <b>{value.reliability.toFixed(0)}%</b></span></div>{scopes.map(scope=><details key={scope.key}><summary>{scope.label} · {signed(scope.value.delta)} · {scope.value.series} series · reliability {scope.value.reliability.toFixed(0)}% · weight {(scope.value.effective_weight*100).toFixed(0)}%</summary><FormEvents events={scope.value.events}/></details>)}<details><summary>Opponent ranking breakdown</summary>{Object.entries(value.opponent_breakdown).map(([key,item])=><div className="team-v3-row" key={key}><b>{{top_1_10:"Top 1–10",top_11_20:"Top 11–20",top_21_30:"Top 21–30",others:"Others",unknown:"Unknown"}[key]??key}</b><span>{item.series} series</span><span>{signed(item.delta)}</span></div>)}</details><p className="formula">Каждая серия создаёт один Performance vs Expectation event. Current Tournament исключён из Recent 60d.</p></section>}

type ActionState =
  | { kind: "idle" }
  | { kind: "probing" }
  | { kind: "refreshing" }
  | {
      kind: "success";
      message: string;
    }
  | { kind: "error"; message: string };

function joinedAtLabel(value: string | null): string {
  if (!value) return "Дата присоединения неизвестна";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата присоединения неизвестна";
  return `В команде с ${date.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  })}`;
}


function RosterGroup({
  label,
  members,
}: {
  label: string;
  members: TeamParticipant[];
}) {
  if (!members.length) {
    return null;
  }
  return (
    <div className="roster-group">
      <small>{label}</small>
      <div className="roster__members">
        {members.map((participant) => (
          <a
            className="roster-member"
            key={`${participant.participant_type}-${participant.bo3_id}`}
            title={participant.country_name || undefined}
            href={`/players/${participant.id}`}
          >
            {participant.image_url && (
              <img alt="" src={participant.image_url} />
            )}
            <span className="roster-member__text">
              <strong>{participant.nickname}</strong>
              <small>{joinedAtLabel(participant.joined_at)}</small>
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}

function TeamCard({ team }: { team: Team }) {
  const players = team.roster.filter(
    (participant) => participant.participant_type === "player",
  );
  const substitutes = team.roster.filter(
    (participant) => participant.participant_type === "substitute",
  );
  const coaches = team.roster.filter(
    (participant) => participant.participant_type === "coach",
  );

  return (
    <article className="team-card">
      <header className="team-card__header">
        <span className="team-card__rank">
          <small>место</small>
          <strong>#{team.current_rank ?? "—"}</strong>
        </span>
        <div className="team-card__state">
          {!team.is_analytics_active && (
            <span className="analytics-status">Не считаем</span>
          )}
          <span
            className={
              team.rank_change && team.rank_change !== 0
                ? team.rank_change > 0
                  ? "change change--up"
                  : "change change--down"
                : "change"
            }
          >
            {rankChangeLabel(team.rank_change)}
          </span>
        </div>
      </header>

      <div className="team-card__identity">
        {team.logo_url ? (
          <img alt="" src={team.logo_url} />
        ) : (
          <span className="team-card__logo-placeholder">
            {team.name.slice(0, 2)}
          </span>
        )}
        <div>
          <h3><a href={`/teams/${team.id}`}>{team.name}</a></h3>
          <span>
            {team.country_name || team.country_code || team.region || "Регион не указан"}
          </span>
        </div>
      </div>

      <div className="team-card__stats">
        <span>
          <small>Очки Valve</small>
          <strong>{formatPoints(team.current_points)}</strong>
        </span>
        <span>
          <small>Игроки</small>
          <strong>{players.length || "—"}</strong>
        </span>
      </div>

      <div className="team-card__roster">
        {team.roster.length ? (
          <>
            <RosterGroup label="Основной состав" members={players} />
            <RosterGroup label="Запасные" members={substitutes} />
            <RosterGroup label="Тренеры" members={coaches} />
          </>
        ) : (
          <span className="roster__empty">состав не синхронизирован</span>
        )}
      </div>

      {team.analyst_factors.length > 0 && (
        <div className="team-card__factors">
          <small>Аналитические факторы</small>
          {team.analyst_factors.map((factor) => (
            <div className={`team-card__factor team-card__factor--${factor.factor_type}`} key={factor.id}>
              <b>{factor.factor_type === "negative" ? "−" : "+"}</b>
              <span>
                {factor.text}
                {factor.valid_until && <small>Действует до {formatDate(factor.valid_until)}</small>}
              </span>
            </div>
          ))}
        </div>
      )}

      <footer className="team-card__footer">
        <span>{team.bo3_slug}</span>
        <span>Синхронизация: {formatDate(team.roster_synced_at)}</span>
      </footer>
    </article>
  );
}

function PlayerPage({ id }: { id: number }) {
  const [player, setPlayer] = useState<Player | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    getPlayer(id).then(setPlayer).catch((value: unknown) => {
      setError(value instanceof Error ? value.message : "Не удалось загрузить игрока.");
    });
  }, [id]);

  const update = async () => {
    setRefreshing(true);
    setError(null);
    try {
      setPlayer(await refreshPlayer(id));
    } catch (value: unknown) {
      setError(value instanceof Error ? value.message : "Не удалось обновить игрока.");
    } finally {
      setRefreshing(false);
    }
  };

  if (error && !player) return <main className="page"><a href="/">← К командам</a><div className="empty-state empty-state--error">{error}</div></main>;
  if (!player) return <main className="page"><div className="empty-state">Загружаю игрока…</div></main>;
  const currentTeam = player.teams.find((team) => team.is_active);
  const fullName = [player.first_name, player.last_name].filter(Boolean).join(" ");
  return (
    <main className="page player-page">
      <a className="back-link" href="/">← К составам команд</a>
      <section className="player-hero">
        {player.image_url ? <img className="player-photo" src={player.image_url} alt={player.nickname} /> : <div className="player-photo player-photo--empty">{player.nickname.slice(0, 2)}</div>}
        <div className="player-heading">
          <p className="eyebrow">Игрок · BO3.gg</p>
          <h1>{player.nickname}</h1>
          <p className="lead">{fullName || "Настоящее имя не указано"} · {player.country_name || player.country_code || "страна не указана"}</p>
          <div className="player-team-status">
            <strong>{currentTeam?.name || player.teams[0]?.name || "Без команды"}</strong>
            <span className={currentTeam ? "status-active" : "status-former"}>{currentTeam ? "активный игрок команды" : "бывший игрок команды"}</span>
          </div>
        </div>
        <button className="button button--primary" disabled={refreshing} onClick={() => void update()}>{refreshing ? "Обновляю…" : "Обновить из BO3.gg"}</button>
      </section>
      {error && <div className="notice notice--error">{error}</div>}
      <section className="player-grid">
        <article className="metric-card"><span>Avg BO3.gg</span><strong>{player.bo3_avg_rating === null ? "—" : Number(player.bo3_avg_rating).toFixed(2)}</strong></article>
        <article className="metric-card internal-rating-card" title="Группа соперника определяется по его месту на дату матча. Если исторических данных нет, используется текущее место."><span>Внутренний рейтинг</span>{[["Общий", player.internal_rating, player.internal_rating_maps_count, player.internal_rating_rounds_count], ["Против Top 1–15", player.internal_rating_top15, player.internal_rating_top15_maps_count, player.internal_rating_top15_rounds_count], ["Против Top 16–30", player.internal_rating_top16_30, player.internal_rating_top16_30_maps_count, player.internal_rating_top16_30_rounds_count]].map(([label, rating, maps, rounds]) => <div className="internal-rating-row" key={String(label)}><span>{label}</span><strong>{rating === null ? "—" : Number(rating).toFixed(2)}</strong><small>{rating === null ? "Нет данных" : `${maps} карт · ${rounds} раундов`}</small></div>)}</article>
        <article className="metric-card"><span>Сила игрока V2</span><strong>{player.player_strength ?? "—"}<small>/100</small></strong><small>Надёжность данных: {player.player_strength_reliability === null ? "—" : `${(player.player_strength_reliability * 100).toFixed(0)}%`} · модель {player.player_strength_model_version ?? "—"}</small></article>
        {player.igl&&<><article className="metric-card"><span>IGL Strength</span><strong>{player.igl.score.toFixed(1)}<small>/100</small></strong><small>Отдельно от индивидуальной силы · confidence {(player.igl.reliability*100).toFixed(0)}%</small></article><article className="metric-card"><span>Captain Strength</span><strong>{player.captain_strength?.toFixed(1)??"—"}<small>/100</small></strong><small>35% Player + 65% IGL</small></article></>}
        <article className="metric-card"><span>Последнее обновление</span><strong className="metric-date">{formatDate(player.stats_synced_at)}</strong></article>
      </section>
      <section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">player_strength.v3 · candidate</p><h2>Player Strength V3</h2></div><small>Legacy V2.1: {player.player_strength??"—"}</small></div><div className="player-v3-scales"><StrengthScale label="Mechanical" value={player.mechanical_strength_v3} reliability={player.player_strength_v3_breakdown?.mechanical.reliability}/><StrengthScale label="Supporting" value={player.supporting_strength_v3} reliability={player.player_strength_v3_breakdown?.supporting.reliability}/><StrengthScale label="Player Strength" value={player.player_strength_v3} reliability={player.player_strength_v3_reliability}/><StrengthScale label="Round Impact" value={player.round_swing.score} reliability={player.round_swing.confidence}/></div>{player.player_strength_v3_breakdown&&<details><summary>Breakdown и группы соперников</summary>{Object.entries(player.player_strength_v3_breakdown.scopes).filter(([key])=>key!=="unknown").map(([key,scope])=><div className="player-v3-scope" key={key}><strong>{{overall:"Overall",top_1_10:"Top 1–10",top_11_20:"Top 11–20",top_21_30:"Top 21–30",others:"Others"}[key]||key}</strong><span>Mechanical {scope.mechanical.score?.toFixed(1)??"—"}</span><span>Supporting {scope.supporting.score?.toFixed(1)??"—"}</span><small>{scope.sample.maps} карт · {scope.sample.rounds} раундов</small></div>)}</details>}</section>
      <section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">player_form.v3 · standalone</p><h2>Current Player Form</h2></div></div><PlayerForm value={player.player_form_v3}/><details><summary>Metric deltas vs own baseline</summary>{Object.entries(player.player_form_v3.metrics).map(([key,item])=><div className="team-v3-row" key={key}><b>{key.replaceAll('_',' ')}</b><span>{signed(item.delta)}</span><small>{item.sample_size} samples</small></div>)}</details></section>
      <PerformanceProfilePanel profile={player.performance_profile} title="Performance Profile"/>
      {player.igl&&<section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">In-game leadership</p><h2>IGL Strength breakdown</h2></div></div><LeadershipFactors value={player.igl}/><p className="formula">Actual {player.igl.actual_performance?.toFixed(1)??"—"} vs expected {player.igl.expected_performance?.toFixed(1)??"—"}; residual {player.igl.management_residual?.toFixed(1)??"—"}. Корреляция, не доказательство причинности.</p></section>}
      <section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">Win probability impact</p><h2>Round Swing</h2></div><span>model {player.round_swing.model?.round_swing_model_version??"—"}</span></div>{player.round_swing.overall?<><div className="team-map-rates"><span>Swing score <strong>{player.round_swing.score?.toFixed(1)??"—"}</strong><small>50 = historical reference median</small></span><span>Swing / round <strong>{player.round_swing.adjusted_per_round?.toFixed(2)??"—"}</strong><small>raw {player.round_swing.raw_per_round?.toFixed(2)} п.п. · confidence {((player.round_swing.confidence??0)*100).toFixed(0)}%</small></span><span>CT / T <strong>{player.round_swing.ct?.toFixed(2)??"—"} / {player.round_swing.t?.toFixed(2)??"—"}</strong><small>{player.round_swing.rounds} rounds</small></span></div><details><summary>Context breakdown</summary><div className="team-map-rates">{(["opening","trade","clutch","postplant","retake"] as const).map(key=><span key={key}>{key}<strong>{player.round_swing[key]?.toFixed(2)??"—"}</strong></span>)}</div></details><details><summary>Maps / opponent rank / recent</summary><div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Scope</span><span>Score</span><span>Adjusted / round</span><span>Rounds</span><span>Confidence</span></div>{Object.entries({...player.round_swing.maps,...player.round_swing.rank_scopes,...player.round_swing.recent}).map(([name,value])=><div className="map-pool-row" key={name}><strong>{name.replaceAll('_',' ')}</strong><span>{value?.score?.toFixed(1)??"—"}</span><span>{value?.adjusted_per_round?.toFixed(2)??"—"}</span><span>{value?.rounds??"—"}</span><span>{value?.confidence===undefined?"—":`${(value.confidence*100).toFixed(0)}%`}</span></div>)}</div></details></>:<div className="empty-state">Round Swing: {player.round_swing.status.replaceAll("_"," ")}</div>}</section>
      <section className="strength-panel">
        <div className="section-heading"><div><p className="eyebrow">Combat</p><h2>Opening / Trades / Clutches</h2></div></div>
        {player.combat.overall ? <div className="team-map-rates"><span>Opening K/D <strong>{player.combat.overall.opening_kills}–{player.combat.overall.opening_deaths}</strong><small>{player.combat.overall.opening_success_rate === null ? "Нет выборки" : `${Number(player.combat.overall.opening_success_rate).toFixed(1)}%`}</small></span><span>Trades <strong>{player.combat.overall.trade_kills}</strong><small>Смертей разменяно: {player.combat.overall.deaths_traded}</small></span><span>Clutches <strong>{player.combat.overall.clutch_wins}/{player.combat.overall.clutch_opportunities}</strong><small>1v1 {player.combat.overall.clutch_1v1_wins}/{player.combat.overall.clutch_1v1_attempts} · 1v2 {player.combat.overall.clutch_1v2_wins}/{player.combat.overall.clutch_1v2_attempts} · 1v3 {player.combat.overall.clutch_1v3_wins}/{player.combat.overall.clutch_1v3_attempts}</small></span></div> : <div className="empty-state">Нужен повторный парсинг demo для combat analytics.</div>}
        <h3>Utility</h3>{player.utility.overall ? <div className="team-map-rates"><span>Utility dmg/round <strong>{player.utility.overall.utility_damage_per_round?.toFixed(2) ?? "—"}</strong><small>HE {player.utility.overall.he_damage_per_round?.toFixed(2) ?? "—"} · Fire {player.utility.overall.fire_damage_per_round?.toFixed(2) ?? "—"}</small></span><span>Flash <strong>{player.utility.overall.enemies_flashed_per_flash?.toFixed(2) ?? "—"}</strong><small>assists/round {player.utility.overall.flash_assists_per_round?.toFixed(2) ?? "—"} · team flashes {player.utility.overall.teammates_flashed}</small></span><span>Utility/round <strong>{player.utility.overall.utility_per_round?.toFixed(2) ?? "—"}</strong><small>HE {player.utility.overall.he_thrown} · Flash {player.utility.overall.flash_thrown} · Smoke {player.utility.overall.smoke_thrown} · Fire {player.utility.overall.fire_thrown}</small></span></div> : <div className="empty-state">Нужен повторный парсинг demo для utility analytics.</div>}
      </section>
      <section className="strength-panel">
        <div className="section-heading"><div><p className="eyebrow">Расшифровка</p><h2>Что повлияло на силу</h2></div></div>
        {player.strength_breakdown ? player.strength_breakdown.factors.map((factor) => (
          <div className="factor" key={factor.key}><span className={`factor__impact factor__impact--${factor.impact > 0 ? "positive" : factor.impact < 0 ? "negative" : "neutral"}`}>{factor.impact > 0 ? "+" : ""}{factor.impact.toFixed(2)}</span><div><strong>{factor.label}: {factor.available ? factor.normalized_score?.toFixed(1) : "нет данных"}</strong><p>{factor.reason}</p><small>Эффективный вес {(factor.effective_weight * 100).toFixed(1)}% · выборка {factor.sample_size ?? "—"} · надёжность {factor.confidence === null ? "—" : `${(factor.confidence * 100).toFixed(0)}%`}</small></div></div>
        )) : <div className="empty-state">BO3.gg пока не предоставил рейтинг. Нажмите «Обновить».</div>}
        {player.strength_breakdown && <small className="formula">Исходная оценка {player.strength_breakdown.raw_score.toFixed(2)} · надёжность {player.strength_breakdown.reliability.toFixed(2)} · поправка {player.strength_breakdown.confidence_adjustment >= 0 ? "+" : ""}{player.strength_breakdown.confidence_adjustment.toFixed(2)} · итог {player.strength_breakdown.final_score.toFixed(2)}</small>}
      </section>
    </main>
  );
}


const roleLabels: Record<string, string> = {
  igl: "IGL",
  awper: "AWPer",
  rifler: "Rifler",
};

const confidenceLabels = {
  not_enough_data: "Недостаточно данных",
  low_confidence: "Низкая надёжность",
  medium_confidence: "Средняя надёжность",
  high_confidence: "Высокая надёжность",
};

const mapWarningLabels: Record<string, string> = {
  small_sample: "Маленькая выборка: вывод может заметно измениться.",
  stale_data: "Данные теряют актуальность.",
  very_stale_data: "Последняя карта сыграна более 90 дней назад.",
  no_matches_against_top_30: "Нет карт против команд Top-30.",
  low_ct_sample: "Меньше 12 раундов за CT.",
  low_t_sample: "Меньше 12 раундов за T.",
  missing_side_data: "Данные одной из сторон отсутствуют.",
};

function TeamPage({ id }: { id: number }) {
  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [teamStrength, setTeamStrength] = useState<TeamDetail["team_strength_v3"] | null>(null);
  const [teamStrengthError, setTeamStrengthError] = useState<string | null>(null);
  const [teamForm, setTeamForm] = useState<TeamDetail["form_v3"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [savingPlayerId, setSavingPlayerId] = useState<number | null>(null);
  const [mapStats, setMapStats] = useState<TeamMapAggregate[]>([]);
  const [mapsLoading, setMapsLoading] = useState(true);
  const [mapsError, setMapsError] = useState<string | null>(null);
  const [mapFilter, setMapFilter] = useState("all");
  const [mapSort, setMapSort] = useState("maps");
  const [mapDetails, setMapDetails] = useState<Record<string, TeamMapDetail>>({});
  const [aggregationLevel, setAggregationLevel] = useState<"organization" | "current_roster">("current_roster");
  const [matchStats, setMatchStats] = useState<TeamMatchStats | null>(null);
  const [veto,setVeto]=useState<TeamVetoProfile|null>(null);
  const [opponentContext,setOpponentContext]=useState<any>(null);

  useEffect(() => {
    let active = true;
    setTeam(null); setError(null); setTeamStrength(null); setTeamStrengthError(null); setTeamForm(null);
    getTeam(id).then((value)=>{if(active)setTeam(value)}).catch((value: unknown) => {
      if(active)setError(value instanceof Error ? value.message : "Не удалось загрузить команду.");
    });
    void getTeamStrengthV3(id).then((value)=>{if(active)setTeamStrength(value)}).catch((value:unknown) => {
      if(active)setTeamStrengthError(value instanceof Error?value.message:"Team Strength V3 недоступен.");
    });
    void getTeamFormV3(id).then((value)=>{if(active)setTeamForm(value)}).catch(() => undefined);
    return ()=>{active=false};
  }, [id]);

  useEffect(() => {
    setMapDetails({});
    setMapsLoading(true); setMapsError(null);
    getTeamMaps(id, aggregationLevel).then((value) => setMapStats(value.maps)).catch((value: unknown) => {
      setMapStats([]);
      setMapsError(value instanceof Error ? value.message : "Не удалось загрузить статистику карт.");
    }).finally(() => setMapsLoading(false));
  }, [id, aggregationLevel]);

  useEffect(() => { void getTeamMatchStats(id, aggregationLevel).then(setMatchStats).catch(() => setMatchStats(null)); }, [id, aggregationLevel]);
  useEffect(() => { void getTeamVeto(id, aggregationLevel).then(setVeto).catch(() => setVeto(null)); }, [id, aggregationLevel]);
  useEffect(() => { void getOpponentContext(id).then(setOpponentContext).catch(() => setOpponentContext(null)); }, [id]);

  if (error) return <main className="page"><a className="back-link" href="/">← К командам</a><div className="empty-state empty-state--error">{error}</div></main>;
  if (!team) return <main className="page"><div className="empty-state">Загружаю команду…</div></main>;

  const activePlayers = team.roster.filter(
    (member) => member.participant_type === "player" && member.is_active && !member.left_at,
  );
  const coaches = team.roster.filter(
    (member) => member.participant_type === "coach" && member.is_active && !member.left_at,
  );
  const strength = team.strength;
  const visibleMaps = mapStats.filter((item) => {
    if (mapFilter === "min3") return item.all.maps_played >= 3;
    if (mapFilter === "min5") return item.all.maps_played >= 5;
    if (mapFilter === "fresh") return item.all.freshness_label === "fresh";
    return true;
  }).sort((a, b) => {
    if (mapSort === "strength") return (b.strength.map_strength_score ?? -1) - (a.strength.map_strength_score ?? -1);
    if (mapSort === "winrate") return (b.all.map_win_rate ?? -1) - (a.all.map_win_rate ?? -1);
    if (mapSort === "ct") return (b.all.ct.win_rate ?? -1) - (a.all.ct.win_rate ?? -1);
    if (mapSort === "t") return (b.all.t.win_rate ?? -1) - (a.all.t.win_rate ?? -1);
    if (mapSort === "date") return (b.all.last_match_date ?? "").localeCompare(a.all.last_match_date ?? "");
    return b.all.maps_played - a.all.maps_played;
  });

  async function changeRole(
    playerId: number,
    role: TeamParticipant["role"],
  ) {
    setSavingPlayerId(playerId);
    setRoleError(null);
    try {
      setTeam(await updatePlayerRole(id, playerId, role));
    } catch (value: unknown) {
      setRoleError(
        value instanceof Error ? value.message : "Не удалось сохранить роль.",
      );
    } finally {
      setSavingPlayerId(null);
    }
  }

  function loadMapDetail(mapName: string) {
    if (mapDetails[mapName]) return;
    void getTeamMapDetail(id, mapName, aggregationLevel).then((value) => {
      setMapDetails((current) => ({ ...current, [mapName]: value }));
    });
  }

  return (
    <main className="page team-page">
      <nav className="page-links"><a className="back-link" href="/">← К командам</a><a className="back-link" href={`/compare?team_a=${team.id}`}>Сравнение команд →</a></nav>
      <section className="team-hero">
        {team.logo_url ? <img src={team.logo_url} alt="" /> : <div className="team-hero__logo">{team.name.slice(0, 2)}</div>}
        <div>
          <p className="eyebrow">Карточка команды · #{team.current_rank ?? "—"}</p>
          <h1>{team.name}</h1>
          <p className="lead">{team.country_name || team.country_code || team.region || "Регион не указан"}</p>
        </div>
        <div className="team-strength-score"><small>Сила команды {strength.model_version.toUpperCase()}</small><strong>{strength.team_strength_score.toFixed(2)}</strong><span>/100 · надёжность {(strength.reliability * 100).toFixed(0)}%</span></div>
      </section>

      <section className="team-metrics">
        <article className="metric-card"><span>Активных игроков</span><strong>{strength.active_players_count}<small>/5</small></strong></article>
        <article className="metric-card"><span>Средняя сила игроков</span><strong>{strength.base_player_score.toFixed(2)}</strong></article>
        <article className="metric-card"><span>Исходная → итоговая</span><strong className="metric-adjustment">{strength.raw_score.toFixed(2)} → {strength.final_score.toFixed(2)}</strong></article>
      </section>

      {teamStrength?.components&&<TeamStrengthV3Panel team={{...team,team_strength_v3:teamStrength}}/>}
      {!teamStrength&&!teamStrengthError&&<section className="strength-panel"><div className="empty-state">Загружаю Team Strength V3…</div></section>}
      {teamStrengthError&&<section className="strength-panel"><div className="empty-state empty-state--error">{teamStrengthError}</div></section>}
      {teamForm?.recent_60d&&<TeamFormV3CurrentPanel team={{...team,team_strength_v3:teamStrength??team.team_strength_v3,form_v3:teamForm}}/>}

      <TeamFormContextBlock context={team.form_context}/>

      <MapsV3Panel teamId={id} legacy={mapStats}/>

      <AnalystFactorsPanel teamId={team.id} roster={team.roster} initial={team.analyst_factors} />

      {opponentContext&&<section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">{opponentContext.version} · candidate</p><h2>Форма с учётом силы соперников</h2></div><div><b>Raw {opponentContext.raw_form_score.toFixed(1)}</b> → <b>Adjusted {opponentContext.opponent_adjusted_form_score.toFixed(1)}</b></div></div><div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Соперник</span><span>Счёт</span><span>Сила соперника</span><span>Качество результата</span></div>{opponentContext.matches.slice(0,8).map((x:any)=><div className="map-pool-row" key={x.match_id}><strong>{x.opponent.name||x.opponent.id}</strong><span>{x.series_score}</span><span>{x.opponent_dynamic_strength.toFixed(1)} <small>reliability {(x.opponent_reliability*100).toFixed(0)}%</small></span><span>{x.result_quality_label.replaceAll("_"," ")}</span></div>)}</div><p className="formula">Dynamic SoS {opponentContext.dynamic_sos_score?.toFixed(1)??"—"} · Tournament adjusted {opponentContext.tournament_opponent_adjusted_form_score?.toFixed(1)??"нет матчей"}. Только матчи строго до даты расчёта.</p></section>}
      <section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">Standalone analytics</p><h2>Leadership</h2></div></div><div className="h2h-grid"><article className="h2h-card"><h3>IGL</h3>{team.leadership.igl?<><a href={`/players/${team.leadership.igl.player_id}`}><strong>{team.leadership.igl.name}</strong></a><div className="team-map-rates"><span>Player Strength <b>{team.leadership.igl.player_strength??"—"}</b></span><span>IGL Strength <b>{team.leadership.igl.score.toFixed(1)}</b></span><span>Captain Strength <b>{team.leadership.igl.captain_strength?.toFixed(1)??"—"}</b></span></div><LeadershipFactors value={team.leadership.igl}/></>:<p>Активная роль IGL достоверно не назначена.</p>}</article><article className="h2h-card"><h3>Coach</h3>{team.leadership.coach?<><a href={`/players/${team.leadership.coach.id}`}><strong>{team.leadership.coach.name}</strong></a><div className="team-map-rates"><span>Coach Impact <b>{team.leadership.coach.score.toFixed(1)}</b></span><span>Confidence <b>{(team.leadership.coach.reliability*100).toFixed(0)}%</b></span><span>Maps <b>{team.leadership.coach.sample.maps}</b></span></div><LeadershipFactors value={team.leadership.coach}/></>:<p>Активный coach не определён.</p>}</article></div><p className="formula">Leadership — корреляционная attribution-модель и не входит в Team Strength.</p></section>

      <section className="strength-panel team-match-panel"><div className="section-heading"><div><p className="eyebrow">Серии</p><h2>Матчи</h2></div><a className="back-link" href={`/matches?team_id=${id}`}>Все серии →</a></div>{matchStats ? <><div className="team-match-summary"><article><span>Всего</span><strong>{matchStats.all.matches_played}</strong></article><article><span>Победы</span><strong>{matchStats.all.matches_won}</strong></article><article><span>Поражения</span><strong>{matchStats.all.matches_lost}</strong></article><article><span>Winrate</span><strong>{matchStats.all.match_win_rate === null ? "—" : `${matchStats.all.match_win_rate.toFixed(1)}%`}</strong></article></div><div className="team-match-breakdown"><span>BO1: <b>{matchStats.by_format.bo1.matches_won}–{matchStats.by_format.bo1.matches_lost}</b></span><span>BO3: <b>{matchStats.by_format.bo3.matches_won}–{matchStats.by_format.bo3.matches_lost}</b></span><span>BO5: <b>{matchStats.by_format.bo5.matches_won}–{matchStats.by_format.bo5.matches_lost}</b></span><span>LAN: <b>{matchStats.by_context.lan.matches_won}–{matchStats.by_context.lan.matches_lost}</b></span><span>Playoff: <b>{matchStats.by_context.playoff.matches_won}–{matchStats.by_context.playoff.matches_lost}</b></span><span>Final: <b>{matchStats.by_context.final.matches_won}–{matchStats.by_context.final.matches_lost}</b></span></div></> : <div className="empty-state">Статистика матчей пока недоступна.</div>}</section>

      <section className="strength-panel"><div className="section-heading"><div><p className="eyebrow">Veto</p><h2>Map Veto Profile</h2></div><span>confidence {veto?.veto_confidence.toFixed(0)??"—"}</span></div>{!veto||veto.sample.series===0?<div className="empty-state">Исторический veto отсутствует для выбранного scope.</div>:<div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Карта</span><span>Pick / first</span><span>Ban / first</span><span>Performance</span><span>Сигнал</span></div>{[...veto.maps].filter(m=>m.active||m.veto_appearances>0).sort((a,b)=>(b.pick.rate??0)+(b.ban.rate??0)-(a.pick.rate??0)-(a.ban.rate??0)).map(m=><div className="map-pool-row" key={m.map_name}><strong>{m.map_name}{!m.active&&<small>inactive · historical</small>}</strong><span>{m.pick.rate?.toFixed(1)??"—"}% / {m.pick.first_pick_rate?.toFixed(1)??"—"}%</span><span>{m.ban.rate?.toFixed(1)??"—"}% / {m.ban.first_ban_rate?.toFixed(1)??"—"}%</span><span><small>Own {m.pick.win_rate?.toFixed(1)??"—"}% · Opp {m.opponent_pick.win_rate?.toFixed(1)??"—"}% · Decider {m.decider.win_rate?.toFixed(1)??"—"}%</small></span><span>{m.is_likely_permaban?"Likely permaban":`pick pref ${m.pick_preference_score?.toFixed(0)??"—"}`}</span></div>)}</div>}<p className="formula">Preference и performance отделены от Map Strength. Sample: {veto?.sample.series??0} серий.</p></section>

      <section className="strength-panel team-map-panel">
        <div className="section-heading"><div><p className="eyebrow">Аналитика</p><h2>Статистика по картам</h2></div></div>
        <div className="team-map-controls">
          <div className="roster-toggle"><button className={aggregationLevel === "current_roster" ? "button button--primary" : "button"} onClick={() => setAggregationLevel("current_roster")}>Текущий состав</button><button className={aggregationLevel === "organization" ? "button button--primary" : "button"} onClick={() => setAggregationLevel("organization")}>История организации</button></div>
          <select value={mapFilter} onChange={(event) => setMapFilter(event.target.value)}><option value="all">Все карты</option><option value="min3">Минимум 3 карты</option><option value="min5">Минимум 5 карт</option><option value="fresh">Только свежие</option></select>
          <select value={mapSort} onChange={(event) => setMapSort(event.target.value)}><option value="strength">По силе карты</option><option value="maps">По числу карт</option><option value="winrate">По winrate</option><option value="date">По последней дате</option><option value="ct">По CT winrate</option><option value="t">По T winrate</option></select>
        </div>
        {mapsLoading ? <div className="empty-state">Загружаю map pool…</div> : mapsError ? <div className="empty-state empty-state--error">{mapsError}</div> : visibleMaps.length === 0 ? <div className="empty-state">{aggregationLevel === "current_roster" ? "У текущего состава ещё нет сыгранных карт." : "По картам ещё нет полностью распарсенных демок."}</div> : <div className="team-map-grid">{visibleMaps.map((item) => {
          const percent = (value: number | null) => value === null ? "—" : `${value.toFixed(1)}%`;
          const record = (scope: TeamMapScope | null | undefined) => scope ? `${scope.maps_won}–${scope.maps_lost}` : "—";
          const detail = mapDetails[item.map_name];
          return <details className="team-map-card" key={item.map_name} onToggle={(event) => event.currentTarget.open && loadMapDetail(item.map_name)}>
            <summary><strong>{item.map_name[0].toUpperCase() + item.map_name.slice(1)}</strong><span>{item.all.maps_won}–{item.all.maps_lost} · {percent(item.all.map_win_rate)}</span></summary>
            <div className="map-strength-heading">
              <div>{item.strength.map_strength_score === null ? <><strong>Legacy Map Strength: недостаточно данных</strong><small>Нужно минимум 3 полностью распарсенные карты.</small></> : <strong>Legacy Map Strength: {item.strength.map_strength_score.toFixed(2)} / 100</strong>}</div>
              <span className={`confidence-badge confidence-badge--${item.strength.confidence_level}`}>{confidenceLabels[item.strength.confidence_level]} · {item.strength.confidence_score.toFixed(2)}</span>
            </div>
            <div className="team-map-rates"><span>CT <strong>{percent(item.all.ct.win_rate)}</strong></span><span>T <strong>{percent(item.all.t.win_rate)}</strong></span><span>Раунды <strong>{item.all.rounds_won}–{item.all.rounds_lost}</strong></span></div>
            <div className="team-map-rates"><span>Plant <strong>{percent(item.all.bomb.plant_rate)}</strong></span><span>Postplant <strong>{percent(item.all.bomb.postplant_win_rate)}</strong></span><span>Retake <strong>{percent(item.all.bomb.retake_win_rate)}</strong></span></div>
            {item.all.economy && <div className="team-map-rates"><span>Пистолетные <strong>{percent(item.all.economy.pistol.win_rate)}</strong></span><span>Конверсия <strong>{percent(item.all.economy.conversion.win_rate)}</strong></span><span>Форс-бай <strong>{percent(item.all.economy.force_buy.win_rate)}</strong></span><span>Полный закуп <strong>{percent(item.all.economy.full_buy.win_rate)}</strong></span><span>Анти-эко <strong>{percent(item.all.economy.anti_eco.win_rate)}</strong></span></div>}
            {item.all.combat && <div className="team-map-rates"><span>Opening <strong>{percent(item.all.combat.opening.success_rate)}</strong></span><span>Conversion <strong>{percent(item.all.combat.opening.conversion_rate)}</strong></span><span>Trade rate <strong>{percent(item.all.combat.trade.trade_rate)}</strong></span><span>Clutch WR <strong>{percent(item.all.combat.clutch.win_rate)}</strong></span></div>}
            {item.all.utility && <div className="team-map-rates"><span>Utility dmg/round <strong>{item.all.utility.utility_damage_per_round?.toFixed(2) ?? "—"}</strong></span><span>Enemies/flash <strong>{item.all.utility.enemies_flashed_per_flash?.toFixed(2) ?? "—"}</strong></span><span>Flash assists/round <strong>{item.all.utility.flash_assists_per_round?.toFixed(2) ?? "—"}</strong></span><span>Utility/round <strong>{item.all.utility.utility_per_round?.toFixed(2) ?? "—"}</strong></span></div>}
            <div className="team-map-scopes">{[["Последние 5", item.recent.last_5], ["Последние 10", item.recent.last_10], ["Последние 20", item.recent.last_20], ["Top 15", item.versus.top_15], ["Top 16–30", item.versus.top_16_30], ["Тир 2–3", item.versus.tier_2_3]] .map(([label, scope]) => { const value = scope as TeamMapScope | null; return <span key={label as string}>{label as string}: <b>{record(value)}</b><small> Plant {percent(value?.bomb.plant_rate ?? null)} · PP {percent(value?.bomb.postplant_win_rate ?? null)} · Retake {percent(value?.bomb.retake_win_rate ?? null)}</small></span>; })}</div>
            <div className="team-map-scopes">{[["Последние 5", item.recent.last_5], ["Последние 10", item.recent.last_10], ["Последние 20", item.recent.last_20], ["Top 15", item.versus.top_15], ["Top 16–30", item.versus.top_16_30], ["Тир 2–3", item.versus.tier_2_3]].map(([label, scope]) => { const value = scope as TeamMapScope | null; return <span key={`economy-${label as string}`}>{label as string} — экономика<small>Пистолетные {percent(value?.economy?.pistol.win_rate ?? null)} · Конверсия {percent(value?.economy?.conversion.win_rate ?? null)} · Форс {percent(value?.economy?.force_buy.win_rate ?? null)} · Полный {percent(value?.economy?.full_buy.win_rate ?? null)} · Анти-эко {percent(value?.economy?.anti_eco.win_rate ?? null)}</small></span>; })}</div>
            <div className="team-map-rates"><span>Plants <strong>{item.all.bomb.plants} / {item.all.bomb.t_rounds_played}</strong></span><span>Postplant <strong>{item.all.bomb.postplant_wins}–{item.all.bomb.postplant_losses}</strong> · explosions {item.all.bomb.explosions}</span><span>Retake <strong>{item.all.bomb.retake_wins}–{item.all.bomb.retake_losses}</strong> · defuses {item.all.bomb.defuses}</span></div>
            {item.all.economy && <div className="team-map-rates"><span>Эко <strong>{percent(item.all.economy.eco.win_rate)}</strong></span><span>Полный против полного <strong>{percent(item.all.economy.full_buy_vs_full_buy.win_rate)}</strong></span><span>Камбэк во втором раунде <strong>{percent(item.all.economy.second_round_comeback.win_rate)}</strong></span><span>Сохранения <strong>{item.all.economy.save.status === "not_parsed" ? "нет надёжных данных" : item.all.economy.save.rounds}</strong></span></div>}
            {item.all.combat && <div className="team-map-rates"><span>Recovery <strong>{percent(item.all.combat.opening.recovery_rate)}</strong></span><span>CT opening <strong>{item.all.combat.opening.ct_kills}–{item.all.combat.opening.ct_deaths}</strong></span><span>T opening <strong>{item.all.combat.opening.t_kills}–{item.all.combat.opening.t_deaths}</strong></span><span>1vX <strong>{Object.values(item.all.combat.clutch.breakdown).reduce((sum, value) => sum + value.wins, 0)}/{Object.values(item.all.combat.clutch.breakdown).reduce((sum, value) => sum + value.attempts, 0)}</strong></span></div>}
            <small>{item.all.maps_played} карт · Последняя: {item.all.last_match_date ? new Date(item.all.last_match_date).toLocaleDateString("ru-RU") : "дата неизвестна"} · Выборка: {item.all.sample_size_label} · Свежесть: {item.all.freshness_label}</small>
            {item.strength.factors.length > 0 && <div className="map-strength-factors"><b>Из чего сложилась оценка</b>{item.strength.factors.map((factor) => <div key={factor.code}><span>{factor.label}</span><strong>{factor.score === null ? "—" : factor.score.toFixed(2)}</strong><em>{factor.impact >= 0 ? "+" : ""}{factor.impact.toFixed(2)}</em><small>{factor.explanation}</small></div>)}</div>}
            {item.strength.warnings.map((warning) => <p className="map-warning" key={warning}>{mapWarningLabels[warning] ?? warning}</p>)}
            {detail && <div className="team-map-matches"><b>{aggregationLevel === "current_roster" ? "Последние игры текущего состава" : "Последние карты организации"}</b>{detail.recent_matches.map((match) => <div key={match.demo_file_id}><span>{match.match_date ? new Date(match.match_date).toLocaleDateString("ru-RU") : "Дата неизвестна"}</span><span>{match.opponent_team_name ?? "Неизвестный соперник"}{match.opponent_rank ? ` (#${match.opponent_rank})` : ""}</span><strong className={match.result === "win" ? "match-win" : "match-loss"}>{match.score_for}:{match.score_against}</strong></div>)}</div>}
          </details>;
        })}</div>}
        <p className="formula">Сила карты строится из сохранённых агрегатов результатов, раундов, сторон и матчей против Top-30. Надёжность стягивает малую или устаревшую выборку к нейтральной оценке 50.</p>
      </section>

      <section className="team-detail-grid">
        <article className="strength-panel team-roster-panel">
          <div className="section-heading"><div><p className="eyebrow">Ростер</p><h2>Игроки</h2></div><span>{activePlayers.length} активных</span></div>
          <div className="team-player-list">
            {activePlayers.map((player) => (
              <div className="team-player-card" key={player.id}>
                {player.image_url ? <img src={player.image_url} alt="" /> : <span>{player.nickname.slice(0, 2)}</span>}
                <div>
                  <a href={`/players/${player.id}`}><strong>{player.nickname}</strong></a>
                  <small>{player.role ? roleLabels[player.role] ?? "Роль не назначена" : "Роль не назначена"}</small>
                  <small className="joined-at">{joinedAtLabel(player.joined_at)}</small>
                </div>
                <div className="team-player-v3"><StrengthScale label="Mechanical" value={player.mechanical_strength_v3} reliability={player.player_strength_v3_breakdown?.mechanical.reliability}/><StrengthScale label="Supporting" value={player.supporting_strength_v3} reliability={player.player_strength_v3_breakdown?.supporting.reliability}/><StrengthScale label="Player Strength V3" value={player.player_strength_v3} reliability={player.player_strength_v3_reliability}/><StrengthScale label="Round Impact" value={player.round_impact} reliability={player.round_impact_reliability}/><small>Legacy V2.1: {player.player_strength??"—"}</small>{player.player_strength_v3_breakdown&&<details><summary>Opponent breakdown</summary>{([['overall','Overall'],['top_1_10','Top 1–10'],['top_11_20','Top 11–20'],['top_21_30','Top 21–30'],['others','Others']] as const).map(([key,label])=>{const scope=player.player_strength_v3_breakdown!.scopes[key];return <p key={key}><b>{label}</b>: M {scope?.mechanical.score?.toFixed(1)??"—"} · S {scope?.supporting.score?.toFixed(1)??"—"} <small>{scope?.sample.maps??0} maps</small></p>})}</details>}</div>
                <label className="role-picker">
                  <span>Роль</span>
                  <select
                    value={player.role && roleLabels[player.role] ? player.role : ""}
                    disabled={savingPlayerId === player.id}
                    onChange={(event) => void changeRole(
                      player.id,
                      (event.target.value || null) as TeamParticipant["role"],
                    )}
                  >
                    <option value="">Не назначена</option>
                    {Object.entries(roleLabels).map(([value, label]) => (
                      <option value={value} key={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <div className="player-ratings"><span><small>Avg BO3.gg</small>{player.bo3_avg_rating === null ? "—" : Number(player.bo3_avg_rating).toFixed(2)}</span><span className="compact-internal" title={`Общий: ${player.internal_rating_maps_count} карт, ${player.internal_rating_rounds_count} раундов; Top 15: ${player.internal_rating_top15_maps_count} карт, ${player.internal_rating_top15_rounds_count} раундов; Top 16–30: ${player.internal_rating_top16_30_maps_count} карт, ${player.internal_rating_top16_30_rounds_count} раундов`}><small>Внутренний</small>{player.internal_rating === null ? "—" : Number(player.internal_rating).toFixed(2)}<em>Top 15: {player.internal_rating_top15 === null ? "—" : Number(player.internal_rating_top15).toFixed(2)} · Top 16–30: {player.internal_rating_top16_30 === null ? "—" : Number(player.internal_rating_top16_30).toFixed(2)}</em></span><span><small>Сила</small>{player.player_strength ?? "—"}</span></div>
              </div>
            ))}
          </div>
          {roleError && <div className="empty-state empty-state--error">{roleError}</div>}
          <div className="coach-list"><small>Тренер</small>{coaches.length ? coaches.map((coach) => <span className="coach-member" key={coach.id}><a href={`/players/${coach.id}`}>{coach.nickname}</a><small>{joinedAtLabel(coach.joined_at)}</small></span>) : <span>не указан</span>}</div>
        </article>

        <article className="strength-panel team-factors-panel">
          <div className="section-heading"><div><p className="eyebrow">Расчёт силы</p><h2>{strength.calculation}</h2></div></div>
          {strength.factors.map((factor) => (
            <div className="team-factor" key={factor.code}>
              <span className={`team-factor__value team-factor__value--${factor.kind}`}>{factor.impact > 0 ? "+" : ""}{factor.impact.toFixed(2)}</span>
              <div><strong>{factor.label}: {factor.available ? factor.normalized_score?.toFixed(1) : "нет данных"}</strong><p>{factor.reason}</p><small>Эффективный вес {(factor.effective_weight * 100).toFixed(1)}% · выборка {factor.sample_size ?? "—"} · надёжность {factor.confidence === null ? "—" : `${(factor.confidence * 100).toFixed(0)}%`}</small></div>
            </div>
          ))}
          {strength.notes.length > 0 && <ul className="strength-notes">{strength.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
        </article>
      </section>
    </main>
  );
}

function formatPoints(
  value: Team["current_points"],
): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 1,
  }).format(Number(value));
}


function formatDate(value: string | null): string {
  if (!value) {
    return "ещё не запускалось";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: value.includes("T")
      ? "short"
      : undefined,
  }).format(new Date(value));
}


function rankChangeLabel(
  value: number | null,
): string {
  if (value === null) {
    return "нет данных";
  }
  if (value > 0) {
    return `↑ ${value}`;
  }
  if (value < 0) {
    return `↓ ${Math.abs(value)}`;
  }
  return "без изменений";
}


export default function App() {
  const mapV3Match = window.location.pathname.match(/^\/teams\/(\d+)\/maps\/([^/]+)\/?$/);
  if (mapV3Match) return <MapV3Page teamId={Number(mapV3Match[1])} mapName={decodeURIComponent(mapV3Match[2])}/>;
  if (/^\/model-sandbox\/?$/.test(window.location.pathname)) return <ModelSandboxPage />;
  if (/^\/matchup-calibration\/?$/.test(window.location.pathname)) return <MatchupCalibrationPage />;
  if (/^\/prediction-history\/?$/.test(window.location.pathname)) return <PredictionHistoryPage />;
  if (/^\/ml\/models\/?$/.test(window.location.pathname)) return <MLModelsPage />;
  if (/^\/ml\/feature-diagnostics\/?$/.test(window.location.pathname)) return <MLFeatureDiagnosticsPage />;
  if (/^\/demos\/?$/.test(window.location.pathname)) return <DemosPage />;
  if (/^\/matches\/?$/.test(window.location.pathname)) return <MatchesPage />;
  const seriesMatch = window.location.pathname.match(/^\/matches\/(\d+)\/?$/);
  if (seriesMatch) return <MatchesPage matchId={Number(seriesMatch[1])} />;
  if (/^\/tournaments\/new\/?$/.test(window.location.pathname)) return <AddTournamentPage />;
  const tournamentMatchNew = window.location.pathname.match(/^\/tournaments\/(\d+)\/matches\/new\/?$/);
  if (tournamentMatchNew) return <AddTournamentMatchPage tournamentId={Number(tournamentMatchNew[1])} />;
  if (/^\/tournaments\/?$/.test(window.location.pathname)) return <TournamentsPage />;
  const tournamentMatch = window.location.pathname.match(/^\/tournaments\/(\d+)\/?$/);
  if (tournamentMatch) return <TournamentsPage tournamentId={Number(tournamentMatch[1])} />;
  if (/^\/compare\/?$/.test(window.location.pathname)) return <TeamComparePage />;
  const playerMatch = window.location.pathname.match(/^\/players\/(\d+)\/?$/);
  if (playerMatch) return <PlayerPage id={Number(playerMatch[1])} />;
  const teamMatch = window.location.pathname.match(/^\/teams\/(\d+)\/?$/);
  if (teamMatch) return <TeamPage id={Number(teamMatch[1])} />;
  const [teams, setTeams] = useState<Team[]>([]);
  const [latestRun, setLatestRun] =
    useState<RankingRun | null>(null);
  const [loadState, setLoadState] =
    useState<LoadState>({ kind: "loading" });
  const [actionState, setActionState] =
    useState<ActionState>({ kind: "idle" });
  const [probe, setProbe] =
    useState<ProbeResult | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [teamPayload, runPayload] =
        await Promise.all([
          getTeams(),
          getLatestRun(),
        ]);
      setTeams(teamPayload);
      setLatestRun(runPayload);
      setLoadState({ kind: "ready" });
    } catch (error: unknown) {
      setLoadState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Не удалось загрузить данные.",
      });
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleProbe = async () => {
    setActionState({ kind: "probing" });
    setProbe(null);

    try {
      const payload = await probeTopTeams();
      setProbe(payload);
      setActionState({
        kind: "success",
        message:
          `BO3.gg вернул ${payload.teams_received}`
          + " корректных команд. БД не изменена.",
      });
    } catch (error: unknown) {
      setActionState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Проверка BO3.gg завершилась ошибкой.",
      });
    }
  };

  const handleRefresh = async () => {
    setActionState({ kind: "refreshing" });

    try {
      const run = await refreshTopTeams();
      setActionState({
        kind: "success",
        message:
          "Top-40 обновлён; места 31–40 сохранены как теневые. "
          + `Активировано: ${run.teams_activated}, `
          + `деактивировано: ${run.teams_deactivated}. `
          + `Профили: ${run.player_profiles_updated} успешно, `
          + `${run.player_profiles_failed} с ошибкой.`,
      });
      await loadData();
      setLatestRun(run);
    } catch (error: unknown) {
      setActionState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Обновление завершилось ошибкой.",
      });
      await loadData();
    }
  };

  const actionInProgress =
    actionState.kind === "probing"
    || actionState.kind === "refreshing";

  return (
    <main className="page">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">C2</span>
          <div>
            <strong>CS2Eye</strong>
            <span>аналитический top‑30</span>
          </div>
        </div>

        <span className="source-badge">
          источник: BO3.gg
        </span>
      </header>

      <nav className="home-navigation"><a className="button" href="/demos">Демки</a><a className="button" href="/compare">Сравнение команд</a><a className="button" href="/prediction-history">Prediction History</a><a className="button" href="/matchup-calibration" title="Read-only сравнение готовых Matchup V1 и V2">Matchup V1 ↔ V2</a><a className="button" href="/model-sandbox" title="Ручные временные эксперименты с Matchup и ML features">Model Sandbox</a><a className="button" href="/ml/models">ML-модели и активация</a><a className="button" href="/ml/feature-diagnostics" title="Read-only диагностика признаков текущей активной ML-модели">ML: диагностика текущей модели</a></nav>

      <section className="hero">
        <div>
          <p className="eyebrow">
            Итерация 01 · команды
          </p>
          <h1>Valve World Top‑30</h1>
          <p className="lead">
            В аналитике участвуют только команды
            текущего рейтинга. Выбывшие команды
            остаются в базе, но автоматически
            становятся неактивными.
          </p>
        </div>

        <div className="hero__actions">
          <button
            className="button button--ghost"
            disabled={actionInProgress}
            onClick={() => {
              void handleProbe();
            }}
            type="button"
          >
            {actionState.kind === "probing"
              ? "Проверяю…"
              : "Проверить BO3.gg"}
          </button>
          <button
            className="button button--primary"
            disabled={actionInProgress}
            onClick={() => {
              void handleRefresh();
            }}
            type="button"
          >
            {actionState.kind === "refreshing"
              ? "Обновляю…"
              : "Обновить всё"}
          </button>
        </div>
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Активные команды</span>
          <strong>{teams.filter((team) => team.is_analytics_active).length}</strong>
          <small>ожидается ровно 30</small>
        </article>
        <article className="summary-card">
          <span>Дата рейтинга</span>
          <strong className="summary-card__date">
            {formatDate(
              latestRun?.ranking_date || null,
            )}
          </strong>
          <small>Valve World Ranking</small>
        </article>
        <article className="summary-card">
          <span>Последнее обновление</span>
          <strong className="summary-card__date">
            {formatDate(
              latestRun?.finished_at || null,
            )}
          </strong>
          <small>
            {latestRun?.status === "failed"
              ? "ошибка импорта"
              : "ручной запуск"}
          </small>
        </article>
      </section>

      {actionState.kind !== "idle" && (
        <div
          className={
            actionState.kind === "error"
              ? "notice notice--error"
              : "notice"
          }
          role="status"
        >
          {actionState.kind === "probing"
            && "Проверяю ответ и состав top‑40…"}
          {actionState.kind === "refreshing"
            && "Обновляю рейтинг, составы и профили игроков…"}
          {(actionState.kind === "success"
            || actionState.kind === "error")
            && actionState.message}
        </div>
      )}

      {latestRun && latestRun.player_profile_failures.length > 0 && (
        <section className="profile-failures">
          <strong>
            Не обновлены профили: {latestRun.player_profile_failures.length}
          </strong>
          <div className="profile-failures__list">
            {latestRun.player_profile_failures.map((failure) => (
              <a href={`/players/${failure.id}`} key={failure.id}>
                <span>{failure.nickname}</span>
                <small>{failure.bo3_slug} · {failure.error}</small>
              </a>
            ))}
          </div>
        </section>
      )}

      {probe && (
        <section className="probe-panel">
          <div>
            <span>Проверка источника</span>
            <strong>
              {probe.teams_received}/40 команд
            </strong>
          </div>
          <p>
            Дата ответа:{" "}
            {formatDate(probe.ranking_date)}.
            Первое место:{" "}
            {probe.teams[0]?.name || "—"}.
          </p>
        </section>
      )}

      <section className="ranking">
        <div className="section-heading">
          <div>
            <p className="eyebrow">
              Активная выборка
            </p>
            <h2>Команды</h2>
          </div>
          <span>
            {teams.length
              ? `${teams.length} записей · ${teams.filter((team) => !team.is_analytics_active).length} не считаем`
              : "данных пока нет"}
          </span>
        </div>

        {loadState.kind === "loading" && (
          <div className="empty-state">
            Загружаю команды…
          </div>
        )}

        {loadState.kind === "error" && (
          <div className="empty-state empty-state--error">
            {loadState.message}
          </div>
        )}

        {loadState.kind === "ready"
          && teams.length === 0 && (
            <div className="empty-state">
              <strong>Top‑30 ещё не загружен</strong>
              <span>
                Сначала можно проверить источник,
                затем нажать «Обновить top‑30».
              </span>
            </div>
          )}

        {teams.length > 0 && (
          <div className="team-grid">
            {teams.map((team) => (
              <TeamCard team={team} key={team.bo3_id} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
