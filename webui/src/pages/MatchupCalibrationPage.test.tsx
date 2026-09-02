import {render,screen} from "@testing-library/react";
import {expect,it,vi} from "vitest";
const api=vi.hoisted(()=>({getMatchupCalibration:vi.fn()}));
vi.mock("../api",()=>api);
import {MatchupCalibrationPage} from "./MatchupCalibrationPage";

it("shows baseline, candidate, factor impacts and flipped matches",async()=>{
 api.getMatchupCalibration.mockResolvedValue({baseline:{version:"matchup_v1",matches:120,correct:80,accuracy:.667,average_winner_margin:8,high_margin_accuracy:.75,margin_buckets:{},error_drivers:{}},candidate:{version:"matchup_v2_candidate",matches:120,correct:85,accuracy:.708,average_winner_margin:7,high_margin_accuracy:.8,margin_buckets:{},error_drivers:{}},delta:{accuracy:.041},sample_size:120,gate_status:"passed",gate_checks:{sufficient_sample:true},flips:{total:1,v2_fixed_v1_error:1,v2_broke_v1_correct:0,net_improvement:1,matches:[{match_id:7,match:"Spirit vs Falcons",baseline_winner_id:2,candidate_winner_id:1,actual_winner_id:1,baseline_score:47,candidate_score:52,result:"fixed",main_changed_factors:[{factor:"h2h",baseline_contribution:2.1,candidate_contribution:.3,change:-1.8}]}]},factor_impact_comparison:{h2h:{baseline_average_absolute_contribution:1.4,candidate_average_absolute_contribution:.5}}});
 render(<MatchupCalibrationPage/>);
 expect(await screen.findByText("matchup_v2_candidate")).toBeTruthy();
 expect(screen.getByText("+4.1 pp")).toBeTruthy();
 expect(screen.getByRole("link",{name:"Spirit vs Falcons"}).getAttribute("href")).toBe("/matches/7");
 expect(screen.getByText("FIXED")).toBeTruthy();
});
