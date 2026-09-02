import {render,screen} from "@testing-library/react";
import {expect,it,vi} from "vitest";
const api=vi.hoisted(()=>({getLatestMLFeatureDiagnostics:vi.fn(),runMLFeatureDiagnostics:vi.fn(),ApiError:class extends Error{status=500}}));
vi.mock("../api",()=>api);
import {MLFeatureDiagnosticsPage} from "./MLFeatureDiagnosticsPage";

it("shows stability, redundancy and ablation diagnostics",async()=>{
  api.getLatestMLFeatureDiagnostics.mockResolvedValue({id:1,model_version:"v1",feature_schema_version:"matchup_features_v2",created_at:"2026-09-01T00:00:00Z",samples:103,diagnostic_train_samples:72,temporal_test_samples:16,quality:{brier_score:.21,log_loss:.61,accuracy:.625},groups:[],multicollinearity_groups:[],features:[{feature:"raw_matchup_centered",group:"matchup",expected_direction:"positive",expected_symmetry:"antisymmetric",coefficient:-.41,coefficient_sign:"negative",sign_mismatch:true,target_correlation:.18,univariate_coefficient:.62,mean:0,std:.2,min:-.4,max:.4,non_zero_samples:70,unique_values:70,missing_count:0,missing_rate:0,near_constant:false,vif:18.2,vif_status:"high",strongest_correlations:[{feature:"matchup_score_centered",correlation:.94,level:"very_high"}],bootstrap:{bootstrap_runs:100,valid_runs:100,positive_sign_runs:43,negative_sign_runs:57,zero_sign_runs:0,expected_sign_rate:.43,coefficient_mean:-.1,coefficient_std:.4,coefficient_p05:-.8,coefficient_p50:-.1,coefficient_p95:.5},stability_status:"unstable",diagnostic_status:"likely_multicollinearity"}],redundancy_candidates:[{features:["matchup_score_centered","raw_matchup_centered"],correlation:.94,level:"very_high"}],ablation:[{feature:"raw_matchup_centered",baseline_brier:.21,without_feature_brier:.20,baseline_log_loss:.61,without_feature_log_loss:.59,baseline_accuracy:.625,without_feature_accuracy:.688,improved_without_feature:true}]});
  render(<MLFeatureDiagnosticsPage/>);
  expect((await screen.findAllByText("raw_matchup_centered")).length).toBeGreaterThan(0);
  expect(screen.getByText("likely multicollinearity")).toBeTruthy();
  expect(screen.getByText(/matchup_score_centered ↔ raw_matchup_centered/)).toBeTruthy();
  expect(screen.getByText("better")).toBeTruthy();
});
