import { useEffect, useState } from "react";

import { compareTeamMaps, compareTeams, compareTeamVeto, getCalculatedVeto, getMatchupScore, getTeamH2H, getTeams, getWinProbability } from "../api";
import { RoleComparisonTable } from "../components/RoleComparisonTable";
import { TeamComparisonSide } from "../components/TeamComparisonSide";
import { InfoTip, Term } from "../components/InfoTip";
import type { CalculatedVeto, MapConfidenceLevel, MatchupScore, Team, TeamComparison, TeamH2HComparison, TeamH2HRosterContext, TeamH2HSlice, TeamMapComparisonItem, TeamMapComparisonResponse, VetoComparison, WinProbability } from "../types";

const confidenceLabels: Record<MapConfidenceLevel, string> = {
  not_enough_data: "Недостаточно данных", low_confidence: "Низкая надёжность",
  medium_confidence: "Средняя надёжность", high_confidence: "Высокая надёжность",
};

function unavailableReason(item: TeamMapComparisonItem, pool: TeamMapComparisonResponse): string {
  if (pool.aggregation_level === "current_roster" && (!pool.team_a.roster_id || !pool.team_b.roster_id)) return "Текущий состав не определён";
  if (item.comparison_status.includes("not_enough_data")) return "У одной или обеих команд меньше трёх карт";
  if (pool.aggregation_level === "current_roster") return "У текущего состава нет карт";
  return "У одной или обеих команд нет данных";
}

const h2hConfidence = { no_data: "Нет данных", low: "Низкая", medium: "Средняя", high: "Высокая" } as const;
const h2hSamples = { no_data: "Нет выборки", very_small: "Очень маленькая", small: "Маленькая", medium: "Средняя", sufficient: "Достаточная" } as const;
const applicabilityLabels = { direct: "прямая", high: "высокая", medium: "средняя", low: "низкая", unknown: "неизвестно" } as const;
const warningLabels: Record<string, string> = {
  very_small_sample: "Очень маленькая выборка", small_sample: "Маленькая выборка",
  stale_history: "История старше 180 дней", very_stale_history: "История старше года",
  partial_roster_data: "Не все исторические составы определены", excluded_invalid_maps: "Некорректные карты исключены",
  future_match_date: "Обнаружена будущая дата карты",
};

function dateLabel(value: string | null): string { return value ? new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU") : "—"; }
function numberLabel(value: number | null, suffix = ""): string { return value === null ? "—" : `${value.toFixed(2)}${suffix}`; }
function MapMetrics({team}:{team:TeamMapComparisonItem["team_a"]}) {
  if (!team) return <span>—<small>Нет данных</small></span>;
  return <span>{team.map_strength_score?.toFixed(2)??"—"}<small>{team.maps_won}–{team.maps_lost} · {team.maps_played} карт</small>
    <small>Установка бомбы {numberLabel(team.bomb.plant_rate,"%")} · Постплэнт {numberLabel(team.bomb.postplant_win_rate,"%")} · Ретейк {numberLabel(team.bomb.retake_win_rate,"%")}</small>
    {team.economy&&<small>Пистолетные {numberLabel(team.economy.pistol.win_rate,"%")} · Конверсия {numberLabel(team.economy.conversion.win_rate,"%")} · Форс-бай {numberLabel(team.economy.force_buy.win_rate,"%")} · Полная закупка {numberLabel(team.economy.full_buy.win_rate,"%")} · Анти-эко {numberLabel(team.economy.anti_eco.win_rate,"%")}</small>}
    {team.combat&&<small>Первая дуэль {numberLabel(team.combat.opening.success_rate,"%")} · Конверсия преимущества {numberLabel(team.combat.opening.conversion_rate,"%")} · Восстановление {numberLabel(team.combat.opening.recovery_rate,"%")} · Размен {numberLabel(team.combat.trade.trade_rate,"%")} · Клатч {numberLabel(team.combat.clutch.win_rate,"%")}</small>}
    {team.utility&&<small>Урон гранатами/раунд {numberLabel(team.utility.utility_damage_per_round)} · Осколочные {numberLabel(team.utility.he_damage_per_round)} · Огонь {numberLabel(team.utility.fire_damage_per_round)} · Ослеплено/флешка {numberLabel(team.utility.enemies_flashed_per_flash)} · Флеш-ассисты/раунд {numberLabel(team.utility.flash_assists_per_round)} · Гранаты/раунд {numberLabel(team.utility.utility_per_round)}</small>}
    <em className={`confidence-badge confidence-badge--${team.confidence_level}`}>{confidenceLabels[team.confidence_level]}</em></span>;
}
const swingStatusLabels:Record<string,string>={complete:"Достаточно данных",partial:"Частичные данные",low_confidence:"Низкая надёжность",not_calculated:"Нет расчёта",model_not_trained:"Модель не обучена"};
const collisionLabels:Record<string,string>={high:"Высокое",medium:"Среднее",low:"Низкое",none:"Нет"};
const availabilityLabels:Record<string,string>={both:"Обе команды",team_a_only:"Только команда A",team_b_only:"Только команда B",none:"Нет данных",available:"Доступно",unavailable:"Недоступно"};

function VetoProbabilityBlock({veto}:{veto:CalculatedVeto|null}) {
  if(!veto)return <section className="map-pool-comparison calculated-veto"><div className="empty-state">Расчёт недоступен.</div></section>;
  const pct=(value:number)=>(value*100).toFixed(0);
  const Opening=({side}:{side:"team_a"|"team_b"})=><article className="h2h-card"><h3>{veto[side].name}</h3>{veto.opening_bans[side].map(item=><div className="opening-ban-row" key={item.map}><span>{item.map}</span><progress max={1} value={item.probability}/><b>{pct(item.probability)}%</b></div>)}</article>;
  return <section className="map-pool-comparison calculated-veto"><div className="section-heading"><div><p className="eyebrow">Exact conditional veto tree · оценка не калибрована</p><h2><Term tip="Вероятности получены точным перебором всех условных веток стандартного BO3 veto.">Вероятные карты BO3</Term></h2></div><span>версия {veto.calculated_veto_model_version}</span></div><h3>Вероятные первые запреты</h3><div className="h2h-grid"><Opening side="team_a"/><Opening side="team_b"/></div><div className="veto-tree-table"><div className="veto-tree-row veto-tree-row--head"><span>Карта</span><span>Первый бан</span><span>Переживёт</span><span>Pick</span><span>Late ban</span><span>Decider</span><span>В BO3</span><span>Надёжность</span></div>{veto.maps.map(m=>{const risk=m.opening_ban_probability>=m.closing_ban_probability&&m.opening_ban_probability>=m.pick_probability?"Главный риск: ранний запрет.":m.closing_ban_probability>m.pick_probability?"Главный риск: поздний запрет.":"Карта часто выбирается после первых запретов.";return <details className="veto-tree-row" key={m.map}><summary><strong>{m.map}</strong><span>{pct(m.opening_ban_probability)}%</span><span>{pct(m.opening_ban_survival_probability)}%</span><span>{pct(m.pick_probability)}%</span><span>{pct(m.closing_ban_probability)}%</span><span>{pct(m.decider_probability)}%</span><span className="veto-probability"><b>{pct(m.series_map_probability)}%</b><progress max={1} value={m.series_map_probability}/></span><span>{pct(m.confidence)}%</span></summary><div className="veto-probability-details"><p><b>{m.map} — {pct(m.series_map_probability)}% попасть в BO3.</b> {risk}</p><p>{veto.team_a.name}: pick {pct(m.pick_by_team_a_probability)}% · historical ban {pct(m.team_a_history.ban_rate)}%.</p><p>{veto.team_b.name}: pick {pct(m.pick_by_team_b_probability)}% · historical ban {pct(m.team_b_history.ban_rate)}%.</p><p>Шанс пережить opening bans — {pct(m.opening_ban_survival_probability)}%. Pick tendencies применяются только в ветках, где карта осталась доступна.</p></div></details>})}</div>{veto.first_actor_assumption&&<p className="formula">Первый действующий неизвестен: порядки A-first и B-first смешаны 50/50.</p>}<p className="formula">`В BO3` означает pick A, pick B или decider, а не гарантию фактически сыгранной карты. Сумма — 300%.</p></section>;
}

function H2HSliceCard({ title, slice, h2h }: { title: string; slice: TeamH2HSlice; h2h: TeamH2HComparison }) {
  const unavailable = slice.status === "current_roster_unavailable";
  const empty = slice.status === "no_meetings" || slice.status === "current_rosters_never_met";
  return <article className="h2h-card">
    <div className="h2h-card__heading"><h3>{title}</h3><span className={`h2h-confidence h2h-confidence--${slice.confidence_level}`}>{h2hConfidence[slice.confidence_level]}</span></div>
    {unavailable ? <p>Невозможно определить личные встречи текущих составов: активная пятёрка одной из команд определена не полностью.</p>
      : empty ? <p>{slice.status === "no_meetings" ? "Очных карт организаций в сохранённых данных нет." : "Текущие составы ещё не встречались."}</p>
      : <>
        <div className="h2h-sides">
          {(["team_a", "team_b"] as const).map((side) => <div key={side}><strong>{h2h[side].name}</strong><b>{numberLabel(slice[side].h2h_rating)}</b><small><Term tip="Оценка очных встреч 0–100 с учётом побед по картам, раундов, давности и размера выборки.">Рейтинг личных встреч / 100</Term></small><span>Победы по картам: {slice[side].maps_won}</span><span>Раунды: {slice[side].rounds_won}</span><span>Доля побед: {numberLabel(slice[side].map_win_rate, "%")}</span></div>)}
        </div>
        <dl className="h2h-meta"><div><dt>Серии</dt><dd>{slice.team_a_series_won}–{slice.team_b_series_won} · сыграно {slice.series_played}</dd></div><div><dt>Карты</dt><dd>{slice.team_a.maps_won}–{slice.team_b.maps_won} · сыграно {slice.maps_played}</dd></div><div><dt>Период</dt><dd>{dateLabel(slice.first_meeting_date)}–{dateLabel(slice.last_meeting_date)}</dd></div><div><dt>Надёжность</dt><dd>{h2hConfidence[slice.confidence_level]} · {slice.confidence_score.toFixed(2)}/100</dd></div><div><dt>Выборка</dt><dd>{h2hSamples[slice.sample_label]}</dd></div><div><dt>Преимущество</dt><dd>{slice.advantage_team_name ? `${slice.advantage_team_name} · ${slice.advantage_diff?.toFixed(2)}` : "Карты близки"}</dd></div></dl>
      </>}
    {title === "Текущие составы" && empty && <p className="formula">Состав №{h2h.team_a.current_roster_id ?? "—"} · состав №{h2h.team_b.current_roster_id ?? "—"}. Исторические личные встречи нельзя автоматически переносить на нынешние пятёрки.</p>}
    {slice.warnings.length > 0 && <div className="h2h-warnings">{slice.warnings.map((warning) => <span key={warning}>{warningLabels[warning] ?? warning}</span>)}</div>}
    {slice.maps.length > 0 && <details><summary>Статистика по картам</summary><div className="h2h-map-table"><div><b>Карта</b><b>Сыграно</b><b>{h2h.team_a.name}</b><b>{h2h.team_b.name}</b><b>Раунды</b><b>Последняя карта</b></div>{slice.maps.map((map) => <div key={map.map_name}><strong>{map.map_name}</strong><span>{map.maps_played}</span><span>{map.team_a_maps_won}</span><span>{map.team_b_maps_won}</span><span>{map.team_a_rounds_won}–{map.team_b_rounds_won}</span><span>{dateLabel(map.last_meeting_date)}</span></div>)}</div></details>}
    {slice.recent_maps.length > 0 && <details open><summary>Последние очные карты</summary><div className="h2h-recent">{slice.recent_maps.map((map) => <article key={map.demo_file_id}><span>{dateLabel(map.match_date)} · {map.tournament}</span><strong>{map.map_name} · {h2h.team_a.name} {map.team_a_score}:{map.team_b_score} {h2h.team_b.name}</strong><small>{map.went_to_overtime ? "Овертайм · " : ""}вес давности {map.recency_weight.toFixed(2)} <InfoTip text="Чем свежее карта, тем сильнее она влияет на итоговую оценку личных встреч."/></small><details><summary>Идентификаторы составов</summary><small>{map.team_a_roster_id ?? "не определён"} / {map.team_b_roster_id ?? "не определён"}</small></details></article>)}</div></details>}
  </article>;
}

function RosterContext({ name, opponent, context }: { name: string; opponent: string; context: TeamH2HRosterContext }) {
  const exp = context.experience, overlap = context.latest_roster_overlap;
  return <article><h4>{name}</h4>{exp.experience_data_status === "unavailable" ? <p>Недостаточно связанных статистик игроков для оценки опыта.</p> : <><p>{exp.players_with_h2h_experience_count} из {exp.current_players_count} текущих игроков уже играли против {opponent}.</p>{exp.experience_data_status === "partial" && <small>Статистика игроков связана не полностью; отсутствие опыта не гарантировано.</small>}</>}
    {overlap.status === "available" ? <p>{overlap.changed_players_count === 0 ? "Состав совпадает с последней очной картой." : `После последней очной карты заменено игроков: ${overlap.changed_players_count}.`}</p> : <p>Состав последней очной карты не определён полностью.</p>}</article>;
}

function RoundSwingBlock({comparison}:{comparison:TeamComparison}) {
  const [map,setMap]=useState("overall");
  const data=map==="overall"?comparison.round_swing_comparison.overall:comparison.round_swing_comparison.per_map[map];
  const maps=Object.keys(comparison.round_swing_comparison.per_map).sort();
  const metrics=[['Средний Swing','avg_swing','Среднее изменение вероятности выиграть раунд, созданное игроками текущей пятёрки за раунд.'],['Два лидера','top2_swing','Средний Swing двух самых результативных по этой метрике игроков состава.'],['Два отстающих','bottom2_swing','Средний Swing двух игроков состава с наименьшим значением метрики.'],['За атаку','t_swing','Swing в раундах за сторону террористов.'],['За защиту','ct_swing','Swing в раундах за сторону спецназа.'],['В первых дуэлях','opening_swing','Swing событий первого убийства в раунде. Это часть общего Swing, а не отдельный бонус.'],['В клатчах','clutch_swing','Swing убийств в ситуациях один против нескольких. Это часть общего Swing.']] as const;
  return <section className="map-pool-comparison"><div className="section-heading"><div><p className="eyebrow">Текущий состав · влияние на вероятность раунда</p><h2><Term tip="Показывает, на сколько процентных пунктов действия игроков меняют вероятность их команды выиграть конкретный раунд.">Влияние на раунд (Round Swing)</Term></h2></div><label>Срез <select value={map} onChange={event=>setMap(event.target.value)}><option value="overall">Все карты</option>{maps.map(name=><option key={name} value={name}>{name}</option>)}</select></label></div>{data?<div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Показатель</span><span>{comparison.team_a.name}</span><span>{comparison.team_b.name}</span><span>Выборка A</span><span>Выборка B</span></div>{metrics.map(([label,key,tip])=><div className="map-pool-row" key={key}><strong><Term tip={tip}>{label}</Term></strong><span>{data.team_a[key]?.toFixed(2)??'—'}</span><span>{data.team_b[key]?.toFixed(2)??'—'}</span><span>{data.team_a.sample.rounds} раундов · {(data.team_a.confidence*100).toFixed(0)}% · {swingStatusLabels[data.team_a.status]??data.team_a.status}</span><span>{data.team_b.sample.rounds} раундов · {(data.team_b.confidence*100).toFixed(0)}% · {swingStatusLabels[data.team_b.status]??data.team_b.status}</span></div>)}</div>:<div className="empty-state">Нет выборки влияния на раунд для этой карты.</div>}<p className="formula">Только текущие пятёрки · {map==='overall'?'все карты':map}. Контекстные показатели входят в общий Swing и повторно не суммируются. Версия модели: {comparison.round_swing_comparison.round_win_model_version??'—'}.</p></section>
}

const matchupFactorTips:Record<string,string>={map_veto:"Главный фактор: сила команд на картах, которые реально или по расчётному вето попадут в серию.",team_strength:"Сравнение готовой Team Strength V2. Повторно сила игроков здесь не рассчитывается.",current_roster_form:"Насколько недавние результаты и текущая пятёрка подтверждают общую силу.",tactical_matchup:"Сопоставление сторон, постплэнта/ретейка, экономики, гранат, разменов и контекстного Round Swing.",h2h:"Личные встречи текущих составов, а при их отсутствии — ослабленная история организаций.",leadership_context:"Небольшой контекстный вклад сравнения капитанов и тренеров."};
const matchupLevels={neutral:"нейтральное",slight:"небольшое",moderate:"умеренное",strong:"сильное"} as const;
const matchupConfidence={low:"низкая",medium:"средняя",high:"высокая"} as const;
const mapRoleLabels:Record<string,string>={team_a_pick:"вероятный выбор команды A",team_b_pick:"вероятный выбор команды B",decider:"решающая карта",ban:"вероятный запрет",remaining:"оставшаяся карта",played:"релевантная карта"};
function MatchupBlock({matchup}:{matchup:MatchupScore}) {
  return <section className="map-pool-comparison matchup-score"><div className="section-heading"><div><p className="eyebrow">Конкретное противостояние · не вероятность победы</p><h2><Term tip="Показывает, насколько особенности одной команды подходят против особенностей другой в заданном формате и вето. 50 — нейтрально.">Оценка противостояния</Term></h2></div><span>{matchup.model_version}</span></div>
    <div className="matchup-score__hero"><div><strong>{matchup.team_a.name}</strong><b>{matchup.team_a.score.toFixed(1)}</b><small>{matchup.team_a.advantage>=0?"+":""}{matchup.team_a.advantage.toFixed(1)} от нейтральных 50</small></div><div><span>Преимущество</span><strong>{matchup.advantage.team_name??"Явного нет"} · {matchupLevels[matchup.advantage.level]}</strong><small>Надёжность {(matchup.reliability*100).toFixed(0)}% · {matchupConfidence[matchup.confidence_level]}</small><em>{matchup.veto.basis==="actual_veto"?"Основа: фактическое вето":"Основа: расчётное вето"} · {matchup.format.toUpperCase()}</em></div><div><strong>{matchup.team_b.name}</strong><b>{matchup.team_b.score.toFixed(1)}</b><small>{matchup.team_b.advantage>=0?"+":""}{matchup.team_b.advantage.toFixed(1)} от нейтральных 50</small></div></div>
    <div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Фактор</span><span>Оценка</span><span>Вес</span><span>Вклад в команду A</span><span>Надёжность</span></div>{matchup.factors.map(f=><div className="map-pool-row" key={f.key}><strong><Term tip={matchupFactorTips[f.key]??f.reason??"Фактор модели противостояния."}>{f.label}</Term></strong><span>{f.available?f.score?.toFixed(1):"Нет данных"}</span><span>{(f.effective_weight*100).toFixed(1)}%</span><span>{f.impact>=0?"+":""}{f.impact.toFixed(2)}</span><span>{f.confidence===null?"—":`${(f.confidence*100).toFixed(0)}%`}</span></div>)}</div>
    {matchup.maps.length>0&&<details><summary>Релевантные карты</summary><div className="map-pool-summary">{matchup.maps.map(m=><span key={m.map}><b>{m.map}</b> · {m.map_matchup_score>=50?matchup.team_a.name:matchup.team_b.name} +{Math.abs(m.map_matchup_score-50).toFixed(1)}<small>{mapRoleLabels[m.role]??m.role} · вес {(m.playability_weight*100).toFixed(0)}% · надёжность {(m.confidence*100).toFixed(0)}%</small></span>)}</div></details>}
    <p className="formula">Оценки обеих команд симметричны и в сумме дают 100. Это аналитическая шкала соответствия сопернику, а не процент победы.</p></section>;
}

function WinProbabilityBlock({prediction,preVeto}:{prediction:WinProbability;preVeto:WinProbability|null}) {
  if(prediction.prediction_status==="model_not_trained")return <section className="map-pool-comparison win-probability"><div className="section-heading"><div><p className="eyebrow">Прогнозная модель</p><h2><Term tip="Вероятность победы серии, обученная на исторических предматчевых состояниях. Это не Matchup Score.">Вероятность победы</Term></h2></div></div><div className="empty-state">Модель Win Probability ещё не обучена или не активирована.</div></section>;
  if(prediction.prediction_status!=="available"||prediction.team_a.probability===null||prediction.team_b.probability===null)return <section className="map-pool-comparison win-probability"><div className="section-heading"><div><p className="eyebrow">Прогнозная модель</p><h2>Вероятность победы</h2></div></div><div className="empty-state">Недостаточно предматчевых данных для надёжной вероятности. Уверенность данных {(prediction.confidence*100).toFixed(0)}%.</div></section>;
  const pre=preVeto?.prediction_status==="available"?preVeto.team_a.probability:null;
  const impact=pre!==null&&pre!==undefined?(prediction.team_a.probability-pre)*100:null;
  return <section className="map-pool-comparison win-probability"><div className="section-heading"><div><p className="eyebrow">Вероятность серии · ML forecast</p><h2><Term tip="Калиброванная модельная вероятность победы серии на основании информации до матча. В отличие от Matchup Score, это именно вероятность.">Вероятность победы</Term></h2></div><span>{prediction.model_version} · данные {(prediction.confidence*100).toFixed(0)}%</span></div><div className="win-probability__hero"><div><strong>{prediction.team_a.name??"Команда A"}</strong><b>{(prediction.team_a.probability*100).toFixed(1)}%</b></div><div><small>{prediction.basis?.analysis_mode==="post_veto"?"После фактического вето":"До вето · расчётное вето"}</small>{impact!==null&&<strong>Влияние вето на команду A: {impact>=0?"+":""}{impact.toFixed(1)} п.п.</strong>}<em>Matchup Score {prediction.basis?.matchup_score.toFixed(1)??"—"}/100 — отдельная аналитическая оценка</em></div><div><strong>{prediction.team_b.name??"Команда B"}</strong><b>{(prediction.team_b.probability*100).toFixed(1)}%</b></div></div>{prediction.limitations.length>0&&<details><summary>Ограничения данных</summary><ul>{prediction.limitations.map(item=><li key={item}>{item}</li>)}</ul></details>}</section>;
}

export function TeamComparePage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamA, setTeamA] = useState(0);
  const [teamB, setTeamB] = useState(0);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [comparison, setComparison] = useState<TeamComparison | null>(null);
  const [h2h, setH2H] = useState<TeamH2HComparison | null>(null);
  const [h2hLoading, setH2HLoading] = useState(false);
  const [h2hError, setH2HError] = useState<string | null>(null);
  const [mapPool, setMapPool] = useState<TeamMapComparisonResponse | null>(null);
  const [mapPoolLevel, setMapPoolLevel] = useState<"organization" | "current_roster">("current_roster");
  const [mapPoolLoading, setMapPoolLoading] = useState(false);
  const [mapPoolError, setMapPoolError] = useState<string | null>(null);
  const [veto,setVeto]=useState<VetoComparison|null>(null);
  const [calculatedVeto,setCalculatedVeto]=useState<CalculatedVeto|null>(null);
  const [matchup,setMatchup]=useState<MatchupScore|null>(null);
  const [winProbability,setWinProbability]=useState<WinProbability|null>(null);
  const [preVetoProbability,setPreVetoProbability]=useState<WinProbability|null>(null);
  const [matchFormat,setMatchFormat]=useState<"bo1"|"bo3"|"bo5">("bo3");
  const [analysisMode,setAnalysisMode]=useState<"pre_veto"|"post_veto">("pre_veto");
  const [seriesId,setSeriesId]=useState(0);
  const [error, setError] = useState<string | null>(null);
  const [analystMode,setAnalystMode]=useState<"relevant"|"all">("relevant");

  async function loadComparison(a: number, b: number) {
    setLoadingComparison(true);
    setMapPoolLevel("current_roster");
    setMapPoolError(null);
    setError(null);
    setH2HLoading(true); setH2HError(null); setH2H(null);
    try {
      const [organization, maps, vetoData, calculated,matchupData,probabilityData,preProbabilityData] = await Promise.all([compareTeams(a, b), compareTeamMaps(a, b), compareTeamVeto(a,b), getCalculatedVeto(a,b),getMatchupScore(a,b,matchFormat,analysisMode,seriesId||undefined),getWinProbability(a,b,matchFormat,analysisMode,seriesId||undefined),analysisMode==="post_veto"?getWinProbability(a,b,matchFormat,"pre_veto",seriesId||undefined):Promise.resolve(null)]);
      setComparison(organization); setMapPool(maps); setVeto(vetoData); setCalculatedVeto(calculated);setMatchup(matchupData);setWinProbability(probabilityData);setPreVetoProbability(preProbabilityData);
    }
    catch (value: unknown) { setComparison(null); setError(value instanceof Error ? value.message : "Не удалось сравнить команды."); }
    finally { setLoadingComparison(false); }
    try { setH2H(await getTeamH2H(a, b)); }
    catch (value: unknown) { setH2HError(value instanceof Error ? value.message : "Не удалось загрузить личные встречи."); }
    finally { setH2HLoading(false); }
  }

  async function changeMapPoolLevel(level: "organization" | "current_roster") {
    setMapPoolLevel(level); setMapPoolLoading(true); setMapPoolError(null);
    try { setMapPool(await compareTeamMaps(teamA, teamB, level)); }
    catch (value: unknown) { setMapPool(null); setMapPoolError(value instanceof Error ? value.message : "Не удалось сравнить набор карт."); }
    finally { setMapPoolLoading(false); }
  }

  useEffect(() => {
    getTeams().then((payload) => {
      const sorted = payload
        .filter((team) => team.is_analytics_active)
        .sort((a, b) => (a.current_rank ?? 999) - (b.current_rank ?? 999));
      setTeams(sorted);
      const query = new URLSearchParams(window.location.search);
      const queryA = Number(query.get("team_a"));
      const queryB = Number(query.get("team_b"));
      const validA = sorted.some((team) => team.id === queryA);
      const validB = sorted.some((team) => team.id === queryB);
      const initialA = validA ? queryA : (sorted[0]?.id ?? 0);
      const initialB = validB && queryB !== initialA ? queryB : (sorted.find((team) => team.id !== initialA)?.id ?? 0);
      setTeamA(initialA); setTeamB(initialB);
      if (validA && validB && queryA !== queryB) void loadComparison(queryA, queryB);
    }).catch((value: unknown) => setError(value instanceof Error ? value.message : "Не удалось загрузить команды."))
      .finally(() => setLoadingTeams(false));
  }, []);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!teamA || !teamB || teamA === teamB) return;
    window.history.replaceState(null, "", `/compare?team_a=${teamA}&team_b=${teamB}`);
    void loadComparison(teamA, teamB);
  }

  const insufficient = !loadingTeams && teams.length > 0 && teams.length < 2;
  return (
    <main className="page compare-page">
      <header className="compare-topbar"><a className="back-link" href="/">← К командам</a><strong>CS2Eye · сравнение</strong></header>
      <section className="compare-heading"><p className="eyebrow">Итерация 05</p><h1>Сравнение команд</h1><p className="lead">Рейтинг, текущие составы и прозрачный расчёт силы по данным из БД.</p></section>
      {loadingTeams ? <div className="empty-state">Загружаю активные команды…</div> : teams.length === 0 ? <div className="empty-state">Активный Top-30 ещё не загружен.</div> : insufficient ? <div className="empty-state">Для сравнения нужны минимум две активные команды.</div> : (
        <form className="compare-form" onSubmit={submit}>
          <label>Команда A<select value={teamA} onChange={(event) => setTeamA(Number(event.target.value))}>{teams.map((team) => <option disabled={team.id === teamB} value={team.id} key={team.id}>#{team.current_rank ?? "—"} · {team.name}</option>)}</select></label>
          <span>против</span>
          <label>Команда B<select value={teamB} onChange={(event) => setTeamB(Number(event.target.value))}>{teams.map((team) => <option disabled={team.id === teamA} value={team.id} key={team.id}>#{team.current_rank ?? "—"} · {team.name}</option>)}</select></label>
          <label>Формат<select value={matchFormat} onChange={event=>setMatchFormat(event.target.value as typeof matchFormat)}><option value="bo1">BO1</option><option value="bo3">BO3</option><option value="bo5">BO5</option></select></label>
          <label>Режим<select value={analysisMode} onChange={event=>setAnalysisMode(event.target.value as typeof analysisMode)}><option value="pre_veto">До вето</option><option value="post_veto">После вето</option></select></label>
          {analysisMode==="post_veto"&&<label>ID серии<input type="number" min="1" value={seriesId||""} onChange={event=>setSeriesId(Number(event.target.value))}/></label>}
          <button className="button button--primary" disabled={!teamA || !teamB || teamA === teamB || loadingComparison || (analysisMode==="post_veto"&&!seriesId)}>Сравнить</button>
        </form>
      )}
      {error && <div className="empty-state empty-state--error">{error}</div>}
      {loadingComparison ? <div className="empty-state">Собираю сравнение команд…</div> : comparison ? <>
        <section className="comparison-hero">
          <TeamComparisonSide side={comparison.team_a} />
          <div className="comparison-advantage"><small>Преимущество</small>{comparison.strength_advantage_team_name ? <><strong>{comparison.strength_advantage_team_name}</strong><span>+{comparison.strength_advantage_diff.toFixed(2)} пункта</span></> : <strong>Явного преимущества нет</strong>}</div>
          <TeamComparisonSide side={comparison.team_b} />
        </section>
        {winProbability&&<WinProbabilityBlock prediction={winProbability} preVeto={preVetoProbability}/>}
        {matchup&&<MatchupBlock matchup={matchup}/>}
        <section className="strength-panel analyst-compare"><div className="section-heading"><div><p className="eyebrow">Human context · отдельно от scoring</p><h2>Аналитические плюсы и минусы</h2></div><div className="roster-toggle"><button className={analystMode==="relevant"?"button button--primary":"button"} onClick={()=>setAnalystMode("relevant")}>Релевантные</button><button className={analystMode==="all"?"button button--primary":"button"} onClick={()=>setAnalystMode("all")}>Все</button></div></div><div className="analyst-compare-grid">{(["team_a","team_b"] as const).map(key=>{const factors=comparison.analyst_context[key][analystMode==="relevant"?"relevant":"all_active"];return <article key={key}><h3>{comparison[key].name}</h3>{(["positive","negative"] as const).map(type=><div key={type}><h4>{type==="positive"?"Плюсы":"Минусы"}</h4>{factors.filter(x=>x.factor_type===type).map(x=><div className={`compare-factor compare-factor--${type}`} key={x.id}><b>{type==="positive"?"+":"−"}</b><span>{x.text}<small>{x.map_name??"Все карты"} · {x.environment==="any"?"Любая среда":x.environment.toUpperCase()} · {x.category?.replaceAll("_"," ")??"без категории"}</small></span></div>)}{!factors.some(x=>x.factor_type===type)&&<p className="muted">Нет факторов</p>}</div>)}</article>})}</div><p className="formula">Факторы не меняют Matchup Score, Win Probability или veto.</p></section>
        <RoleComparisonTable comparison={comparison} />
        <RoundSwingBlock comparison={comparison}/>
        <section className="map-pool-comparison"><div className="section-heading"><div><p className="eyebrow">Отдельная аналитика</p><h2><Term tip="Сравнение влияния капитана и тренера. Блок показывается отдельно и не повышает общую силу команды.">Лидерство</Term></h2></div></div><div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Показатель</span><span>{comparison.team_a.name}</span><span>{comparison.team_b.name}</span><span>Модель A</span><span>Модель B</span></div><div className="map-pool-row"><strong><Term tip="Оценка капитана как внутриигрового лидера по доступным данным о составе и результатах.">Сила капитана (IGL)</Term></strong><span>{comparison.team_a.leadership.igl?.score.toFixed(1)??"—"}</span><span>{comparison.team_b.leadership.igl?.score.toFixed(1)??"—"}</span><span>{comparison.team_a.leadership.igl?.model_version??"—"}</span><span>{comparison.team_b.leadership.igl?.model_version??"—"}</span></div><div className="map-pool-row"><strong><Term tip="Оценка влияния тренера с учётом срока работы и результатов состава.">Влияние тренера</Term></strong><span>{comparison.team_a.leadership.coach?.score.toFixed(1)??"—"}</span><span>{comparison.team_b.leadership.coach?.score.toFixed(1)??"—"}</span><span>{comparison.team_a.leadership.coach?.model_version??"—"}</span><span>{comparison.team_b.leadership.coach?.model_version??"—"}</span></div></div><p className="formula">Лидерство не включено в силу команды или оценку конкретного противостояния.</p></section>
        <section className="map-pool-comparison"><div className="section-heading"><div><p className="eyebrow">История прошлых серий</p><h2><Term tip="Реальные запреты и выборы карт из сохранённых серий. Это история действий команд, а не рекомендация модели.">Исторические привычки вето</Term></h2></div></div>{!veto||veto.team_a.sample.series===0||veto.team_b.sample.series===0?<div className="empty-state">Недостаточно истории veto прошлых серий.</div>:<div className="map-pool-table"><div className="map-pool-row map-pool-row--head"><span>Карта</span><span>{veto.team_a.team_name}</span><span>{veto.team_b.team_name}</span><span><Term tip="Насколько выбор карты одной командой сталкивается с желанием соперника её запретить.">Столкновение</Term></span><span>Доступность</span></div>{veto.maps.filter(m=>m.team_a.active||m.team_b.active).map(m=><div className="map-pool-row" key={m.map_name}><strong>{m.map_name}</strong><span>Выбор {m.team_a.pick.rate?.toFixed(1)??"—"}% · Запрет {m.team_a.ban.rate?.toFixed(1)??"—"}%</span><span>Выбор {m.team_b.pick.rate?.toFixed(1)??"—"}% · Запрет {m.team_b.ban.rate?.toFixed(1)??"—"}%</span><span>{collisionLabels[m.collision]??m.collision}</span><span>{availabilityLabels[m.availability]??m.availability.replaceAll("_"," ")}</span></div>)}</div>}<p className="formula">Только сохранённые реальные выборы и запреты прошлых серий. Очная история вето: {veto?.h2h.series??0} последних серий.</p></section>
        <VetoProbabilityBlock veto={calculatedVeto}/>
        <section className="map-pool-comparison">
          <div className="section-heading"><div><p className="eyebrow">Аналитика карт</p><h2><Term tip="Сопоставление силы команд на каждой карте активного набора с учётом результатов, сторон, объёма и свежести данных.">Сравнение набора карт</Term></h2></div></div>
          <div className="roster-toggle"><button className={mapPoolLevel === "current_roster" ? "button button--primary" : "button"} onClick={() => void changeMapPoolLevel("current_roster")}>Текущие составы</button><button className={mapPoolLevel === "organization" ? "button button--primary" : "button"} onClick={() => void changeMapPoolLevel("organization")}>История организаций</button></div>
          {mapPoolLoading ? <div className="empty-state">Сравниваю карты…</div> : mapPoolError ? <div className="empty-state empty-state--error">{mapPoolError}</div> : !mapPool ? <div className="empty-state">Набор карт ещё не загружен.</div> : mapPool.maps.length === 0 ? <div className="empty-state">{mapPool.status === "current_roster_unavailable" ? "Текущий состав одной из команд не определён." : mapPoolLevel === "current_roster" ? "У текущих составов пока нет карт." : "Для организаций пока нет агрегатов карт."}</div> : <>
            <div className="map-pool-table">
              <div className="map-pool-row map-pool-row--head"><span>Карта</span><span>{mapPool.team_a.name}</span><span>{mapPool.team_b.name}</span><span><Term tip="Команда с большей модельной силой на карте и величина разницы между командами.">Преимущество</Term></span><span><Term tip="Уверенность в оценках обеих команд: зависит от числа карт, раундов, полноты и свежести данных.">Надёжность</Term></span></div>
              {mapPool.maps.map((item) => <div className="map-pool-row" key={item.map_name}>
                <strong>{item.map_name[0].toUpperCase() + item.map_name.slice(1)}</strong>
                <MapMetrics team={item.team_a}/>
                <MapMetrics team={item.team_b}/>
                <span>{item.advantage_team_name ? <><b>{item.advantage_team_name}</b><small>+{item.advantage_diff?.toFixed(2)} · {item.advantage_level === "small" ? "небольшое" : item.advantage_level === "clear" ? "явное" : "сильное"}</small></> : item.comparison_status === "comparable" ? "Карты близки" : unavailableReason(item, mapPool)}</span>
                <span>{item.team_a && item.team_b ? `${item.team_a.confidence_score.toFixed(2)} / ${item.team_b.confidence_score.toFixed(2)}` : "—"}</span>
              </div>)}
            </div>
            <div className="map-pool-summary"><span>Преимущество {mapPool.team_a.name}: <b>{mapPool.summary.team_a_advantage_maps}</b></span><span>Преимущество {mapPool.team_b.name}: <b>{mapPool.summary.team_b_advantage_maps}</b></span><span>Близкие карты: <b>{mapPool.summary.close_maps}</b></span><span>Без достаточных данных: <b>{mapPool.summary.not_comparable_maps}</b></span></div>
          </>}
          <p className="formula">Сравнение описывает сохранённую статистику набора карт и её надёжность. Это не прогноз результата матча или вето.</p>
        </section>
        <section className="h2h-section"><div className="section-heading"><div><p className="eyebrow">Очная аналитика</p><h2><Term tip="История карт и серий, которые эти организации или именно их текущие составы сыграли друг против друга.">Личные встречи</Term></h2></div></div>
          {h2hLoading ? <div className="empty-state">Загружаю очные карты…</div> : h2hError ? <div className="empty-state empty-state--error">{h2hError}</div> : h2h ? <>
            <div className="h2h-grid"><H2HSliceCard title="История организаций" slice={h2h.organizations} h2h={h2h} /><H2HSliceCard title="Текущие составы" slice={h2h.current_rosters} h2h={h2h} /></div>
            <div className="h2h-context"><div className="h2h-card__heading"><h3><Term tip="Показывает, насколько корректно переносить результаты старых встреч организаций на игроков нынешних составов.">Применимость истории к текущим составам</Term></h3><span className={`h2h-applicability h2h-applicability--${h2h.roster_context.history_applicability}`}>{applicabilityLabels[h2h.roster_context.history_applicability]}</span></div><div className="h2h-context-grid"><RosterContext name={h2h.team_a.name} opponent={h2h.team_b.name} context={h2h.roster_context.team_a} /><RosterContext name={h2h.team_b.name} opponent={h2h.team_a.name} context={h2h.roster_context.team_b} /></div>{h2h.insights.length > 0 && <ul>{h2h.insights.map((insight, index) => <li key={`${insight.code}-${index}`}>{insight.text}</li>)}</ul>}</div>
          </> : <div className="empty-state">Личные встречи ещё не загружены.</div>}
          <p className="formula">История описывает сохранённые очные карты и не является прогнозом результата будущей встречи.</p>
        </section>
        <section className="comparison-summary"><p className="eyebrow">Краткий вывод</p><h2>Что показывает сравнение</h2><ul>{comparison.summary_notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul></section>
      </> : !loadingTeams && teams.length >= 2 && !error ? <div className="empty-state">Выберите две команды для сравнения.</div> : null}
    </main>
  );
}
