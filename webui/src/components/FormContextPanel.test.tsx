import {renderToStaticMarkup} from "react-dom/server";
import {describe,expect,it} from "vitest";
import {CompareFormContextBlock,TeamFormContextBlock} from "./FormContextPanel";
import type {FormContext} from "../types";

const context:FormContext={as_of:"2026-08-26",window_days:60,tournament_id:1,tournament_form_score:78,recent_60d_adjusted_form_score:74,strength_of_schedule_score:81,performance_vs_expectation_score:72,tournament_strength_of_schedule_score:84,tournament_reliability:.5,recent_60d_reliability:.75,tournament_matches_count:3,recent_60d_matches_count:9,top5_matches_60d:1,top10_matches_60d:3,top20_matches_60d:5,top30_matches_60d:8,close_series_count:3,upset_wins_count:1,strong_losses_count:1,performed_above_expectation_count:4,performed_below_expectation_count:2,status:"available",tournament_status:"available",cutoff_policy:"event_date < as_of"};

describe("FormContextPanel",()=>{
  it("renders values, counts and help text on team page",()=>{const html=renderToStaticMarkup(<TeamFormContextBlock context={context}/>);expect(html).toContain("Tournament Form");expect(html).toContain("78.0");expect(html).toContain("9 серий за 60 дней");expect(html).toContain("поправкой на силу календаря")});
  it("renders both teams on compare page",()=>{const html=renderToStaticMarkup(<CompareFormContextBlock teamA={context} teamB={{...context,tournament_form_score:61}} nameA="Legacy" nameB="FURIA"/>);expect(html).toContain("Legacy");expect(html).toContain("FURIA");expect(html).toContain("78.0");expect(html).toContain("61.0")});
  it("renders insufficient data",()=>{const html=renderToStaticMarkup(<TeamFormContextBlock context={{...context,status:"insufficient_data",recent_60d_matches_count:0}}/>);expect(html).toContain("Недостаточно недавних серий")});
});
