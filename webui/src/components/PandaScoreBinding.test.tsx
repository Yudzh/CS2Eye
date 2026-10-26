import {cleanup, render, screen} from "@testing-library/react";
import {afterEach, expect, it} from "vitest";
import {PandaScoreBinding} from "./PandaScoreBinding";
afterEach(cleanup);
const value={source:"pandascore",external_id:1752691,received_at:null,checked_at:null,status:"confirmed",error:null,manual:false,link:{"1":3210,"2":3216},proposal:null,provider_api_url:"https://api.pandascore.co/csgo/matches/past?filter[id]=1752691",provider_match:{id:1752691,name:null,status:"finished",begin_at:"2026-10-24T16:22:51Z",scheduled_at:null,league:{id:5442,name:"PGL Masters"},serie:{id:11118,name:"Bucharest",full_name:"Bucharest 2026",year:2026},tournament:{id:22222,name:"Group Stage"},opponents:[{id:3210,name:"G2"},{id:3216,name:"Natus Vincere"}],results:[{team_id:3210,score:0},{team_id:3216,score:2}],winner_id:3216,forfeit:false}};
it("shows source participants, event, identifiers and links without credentials", () => {
  render(<PandaScoreBinding matchId={7} value={value} expanded/>);
  expect(screen.getByRole("heading",{name:"G2 — Natus Vincere"})).toBeTruthy();
  expect(screen.getByText("PGL Masters → Bucharest 2026 → Group Stage")).toBeTruthy();
  expect(screen.getByText(/#1 → #3210/)).toBeTruthy();
  expect(screen.getByRole("link",{name:/Матч PandaScore/}).getAttribute("href")).toBe("/matches/7/pandascore");
  expect(screen.getByRole("link",{name:/Исходный запрос/}).getAttribute("href")).not.toContain("token=");
});
it("distinguishes a manual ID from fetched and reviewed evidence", () => {
  const {rerender}=render(<PandaScoreBinding matchId={7} value={{...value,provider_match:null,status:"linked"}}/>);
  expect(screen.getByText(/данные матча ещё не получены/)).toBeTruthy();
  expect(screen.queryByText("✓ Данные PandaScore получены")).toBeNull();
  rerender(<PandaScoreBinding matchId={7} value={{...value,status:"needs_review"}}/>);
  expect(screen.getByText("Привязка требует проверки")).toBeTruthy();
});
