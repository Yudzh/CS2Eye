// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MapsV3Panel, MapV3Page } from "./MapsV3";
import { getTeamMapsV3, getTeamMapV3, getTeamMapDetail } from "../api";
import type { MapStrengthV3Item } from "../types";
vi.mock("../api",()=>({getTeamMapsV3:vi.fn(),getTeamMapV3:vi.fn(),getTeamMapDetail:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks()});
const emptyMetric={score:null,reliability:0,metrics:{}};
const empty={map:"nuke",is_active_pool:true,score:null,team_strength_v3:82,delta_vs_team:null,status:"NOT_ENOUGH_DATA",flags:["LOW_SAMPLE"],reliability:0,sides:{ct:{...emptyMetric,rounds:0},t:{...emptyMetric,rounds:0}},components:{results_quality:emptyMetric,side_performance:emptyMetric,map_execution:emptyMetric},sample:{maps:0},reliability_breakdown:{},roster_context:{source:"PERMANENT",effective_player_ids:[],permanent_player_ids:[],replacements:[],warnings:[]},results_breakdown:{overall:{...emptyMetric,maps:0,wins:0,losses:0,round_differential:0},groups:{}},performance_profile:{scopes:{overall:{},ct:{},t:{}}}} as unknown as MapStrengthV3Item;
describe("Maps V3",()=>{
 it("loads API and keeps an unplayed map unavailable",async()=>{
  vi.mocked(getTeamMapsV3).mockResolvedValue({team_id:1,as_of:"2026-09-05",model_version:"map_strength.v3",maps:[empty]});
  render(<MapsV3Panel teamId={1} legacy={[]}/>);
  expect(await screen.findByText("NOT_ENOUGH_DATA")).toBeTruthy();
  expect(screen.getByRole("meter",{name:"New Map Strength V3"}).getAttribute("value")).toBe("0");
  expect(screen.queryByText("50.00 /100")).toBeNull();
  expect(screen.getByRole("link",{name:"Подробнее →"}).getAttribute("href")).toBe("/teams/1/maps/nuke");
 });
 it("shows request errors instead of disappearing",async()=>{
  vi.mocked(getTeamMapsV3).mockRejectedValue(new Error("Server unavailable"));
  render(<MapsV3Panel teamId={1} legacy={[]}/>);
  expect((await screen.findByRole("alert")).textContent).toContain("Server unavailable");
 });
 it("opens the map with all three components and separate side meters",async()=>{
  vi.mocked(getTeamMapV3).mockResolvedValue({map_strength_v3:empty});
  vi.mocked(getTeamMapDetail).mockRejectedValue(new Error("legacy unavailable"));
  render(<MapV3Page teamId={1} mapName="nuke"/>);
  expect(await screen.findByText(/1. Results Quality/)).toBeTruthy();
  expect(screen.getByText(/2. Side Performance/)).toBeTruthy();
  expect(screen.getByText(/3. Map Execution/)).toBeTruthy();
  expect(screen.getByRole("meter",{name:"CT SIDE"})).toBeTruthy();
  expect(screen.getByRole("meter",{name:"T SIDE"})).toBeTruthy();
  expect(screen.getByRole("button",{name:"Both"})).toBeTruthy();
 });
});
