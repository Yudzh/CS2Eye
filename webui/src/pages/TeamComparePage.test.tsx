import {render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import type {Team} from "../types";

const api = vi.hoisted(() => ({}));
vi.mock("../api", () => ({
  ...api,
  capturePredictionHistory:vi.fn(), compareTeamMaps: vi.fn(), compareTeams: vi.fn(), compareTeamVeto: vi.fn(),
  getBettingRestrictions: vi.fn(), getCalculatedVeto: vi.fn(), getMatch: vi.fn(), getMatchupScore: vi.fn(),
  getHEKillBacktest: vi.fn(), getHEKillByMap: vi.fn(), getTeamH2H: vi.fn(), getTeams: vi.fn(), getWinProbability: vi.fn(),
}));

import {HEKillByMapBlock, HEKillQualityBlock, missingRequestedTeamIds} from "./TeamComparePage";

describe("compare URL teams", () => {
  it("reports a tournament team missing from the Top-40 list", () => {
    const aurora = {id: 8, name: "Aurora"} as Team;
    expect(missingRequestedTeamIds([aurora], [8, 24])).toEqual([24]);
  });
});

describe("HE Kill V1 quality",()=>{
  it("renders metrics, empty calibration buckets, maps and confidence",()=>{render(<HEKillQualityBlock loading={false} error={null} onLoad={()=>{}} report={{model_version:"he-kill-by-map.v1",metrics:{predictions_count:486,brier_score:.218,avg_predicted_probability:.58,actual_he_kill_rate:.56},calibration:[{bucket:"40–50%",lower_bound:.4,upper_bound:.5,predictions_count:70,brier_score:.23,avg_predicted_probability:.45,actual_he_kill_rate:.47},{bucket:"50–60%",lower_bound:.5,upper_bound:.6,predictions_count:0,brier_score:null,avg_predicted_probability:null,actual_he_kill_rate:null}],by_map:[{map:"ancient",predictions_count:80,brier_score:.2,avg_predicted_probability:.6,actual_he_kill_rate:.58}],by_confidence:[{confidence:"low",predictions_count:20,brier_score:.24,avg_predicted_probability:.5,actual_he_kill_rate:.45},{confidence:"medium",predictions_count:30,brier_score:.21,avg_predicted_probability:.58,actual_he_kill_rate:.57},{confidence:"high",predictions_count:40,brier_score:.18,avg_predicted_probability:.65,actual_he_kill_rate:.67}],predictions:[]}}/>);expect(screen.getByText("486")).toBeTruthy();expect(screen.getByText("0.218")).toBeTruthy();expect(screen.getByText("40–50%")).toBeTruthy();expect(screen.getByText("Ancient")).toBeTruthy();expect(screen.getByText("High")).toBeTruthy();expect(screen.getAllByText("—").length).toBeGreaterThan(0)});
  it("starts as a lazy debug report",()=>{render(<HEKillQualityBlock report={null} loading={false} error={null} onLoad={()=>{}}/>);expect(screen.getByText("Открыть отчёт")).toBeTruthy()});
});

describe("HE Kill probability",()=>{
  const rows=[
    {map:"inferno",probability:.69,confidence:"medium" as const,team_a_sample:9,team_b_sample:11},
    {map:"ancient",probability:.64,confidence:"high" as const,team_a_sample:14,team_b_sample:12},
    {map:"train",probability:.57,confidence:"low" as const,team_a_sample:1,team_b_sample:0},
    {map:"mirage",probability:.51,confidence:"medium" as const,team_a_sample:5,team_b_sample:7},
    {map:"nuke",probability:.47,confidence:"medium" as const,team_a_sample:6,team_b_sample:5},
    {map:"overpass",probability:.43,confidence:"low" as const,team_a_sample:2,team_b_sample:3},
    {map:"dust2",probability:.38,confidence:"medium" as const,team_a_sample:8,team_b_sample:9},
  ];
  it("renders all backend rows in order with percent, confidence and samples",()=>{render(<HEKillByMapBlock rows={rows} nameA="Alpha" nameB="Bravo"/>);const cards=screen.getAllByRole("article");expect(cards).toHaveLength(7);expect(cards.map(card=>card.querySelector("strong")?.textContent)).toEqual(["Inferno","Ancient","Train","Mirage","Nuke","Overpass","Dust2"]);expect(cards[0].textContent).toContain("69%");expect(cards[0].textContent).toContain("Средняя");expect(cards[0].textContent).toContain("sample 9/11")});
  it("renders unavailable state",()=>{render(<HEKillByMapBlock rows={[]} nameA="Alpha" nameB="Bravo"/>);expect(screen.getByText("HE Kill prediction unavailable")).toBeTruthy()});
});
