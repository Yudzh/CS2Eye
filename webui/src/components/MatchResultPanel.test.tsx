import {fireEvent, render, screen, waitFor, cleanup} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
const api=vi.hoisted(()=>({bindMatchResult:vi.fn(),checkMatchResult:vi.fn(),correctMatchResult:vi.fn(),getMatchResultAudit:vi.fn()}));
vi.mock("../api",()=>api);
import {MatchResultPanel} from "./MatchResultPanel";
afterEach(cleanup);
beforeEach(()=>vi.resetAllMocks());
const props={matchId:7,teamA:{id:1,name:"G2"},teamB:{id:2,name:"NAVI"},value:{source:"pandascore",external_id:1752691,received_at:"2026-10-24T18:00:00Z",checked_at:"2026-10-24T18:00:00Z",status:"confirmed",error:null,manual:false,link:null,proposal:null}};
describe("result administration",()=>{
 it("shows provenance and checks saved result",async()=>{
  const changed=vi.fn();api.checkMatchResult.mockResolvedValue({checked:1});
  render(<MatchResultPanel {...props} changed={changed}/>);
  expect(screen.getByRole("link", {name: "Матч PandaScore #1752691 ↗"}).getAttribute("href")).toBe("/matches/7/pandascore");
  fireEvent.click(screen.getByText("Проверить результат"));
  await waitFor(()=>expect(api.checkMatchResult).toHaveBeenCalledWith(7));
  expect(changed).toHaveBeenCalled();
 });
 it("displays safe errors and audit author/reason",async()=>{
  api.checkMatchResult.mockRejectedValue(new Error("PandaScore: ошибка сети"));
  api.getMatchResultAudit.mockResolvedValue({items:[{id:1,at:"2026-10-24T18:00:00Z",actor:"owner",reason:"Проверен счёт",before:{},after:{}}]});
  render(<MatchResultPanel {...props}/>);
  fireEvent.click(screen.getByText("Проверить результат"));
  await waitFor(()=>expect(screen.getByRole("alert").textContent).toContain("ошибка сети"));
  fireEvent.click(screen.getByText("Журнал изменений"));
  await waitFor(()=>expect(screen.getByText(/owner · Проверен счёт/)).toBeTruthy());
 });
 it("submits a correction with actor and reason",async()=>{
  api.correctMatchResult.mockResolvedValue({status:"manual"});render(<MatchResultPanel {...props}/>);
  fireEvent.change(screen.getByLabelText("Карты: G2"),{target:{value:"0"}});
  fireEvent.change(screen.getByLabelText("Карты: NAVI"),{target:{value:"2"}});
  fireEvent.change(screen.getByLabelText("Победитель"),{target:{value:"2"}});
  const form=screen.getByText("Сохранить исправление").closest("form")!;
  fireEvent.change(form.querySelector('[name="actor"]')!,{target:{value:"owner"}});
  fireEvent.change(form.querySelector('[name="reason"]')!,{target:{value:"Проверен счёт"}});
  fireEvent.submit(form);
  await waitFor(()=>expect(api.correctMatchResult).toHaveBeenCalledWith(7,{team_a:0,team_b:2,winner_team_id:2,actor:"owner",reason:"Проверен счёт"}));
 });
});
