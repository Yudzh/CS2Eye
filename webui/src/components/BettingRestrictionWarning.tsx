import type {BettingRestrictions} from "../types";

export function BettingRestrictionWarning({restriction}:{restriction:BettingRestrictions|undefined|null}){
  if(!restriction?.restricted)return null;
  const items=restriction.restrictions?.length?restriction.restrictions:restriction.rule&&restriction.message?[{rule:restriction.rule,message:restriction.message}]:[];
  const titles={navi_no_match_winner_bets:"NAVI RULE",group_stage_no_match_winner_bets:"GROUP STAGE RULE"} as const;
  return <>{items.map(item=><aside className="navi-rule" role="alert" key={item.rule}><strong>⚠️ {titles[item.rule]}</strong><p>{item.message}</p><small>Ручное пользовательское правило · не является выводом модели</small></aside>)}</>;
}
