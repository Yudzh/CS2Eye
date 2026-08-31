import {cleanup, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it} from "vitest";

import {BettingRestrictionWarning} from "./BettingRestrictionWarning";

afterEach(cleanup);

describe("NAVI betting override",()=>{
  it("renders the backend rule prominently",()=>{render(<BettingRestrictionWarning restriction={{restricted:true,rule:"navi_no_match_winner_bets",message:"НЕ СТАВИТЬ НА NAVI И НЕ СТАВИТЬ ПРОТИВ NAVI."}}/>);expect(screen.getByRole("alert").textContent).toContain("NAVI RULE");expect(screen.getByRole("alert").textContent).toContain("НЕ СТАВИТЬ НА NAVI")});
  it("renders nothing for unrestricted matches",()=>{const {container}=render(<BettingRestrictionWarning restriction={{restricted:false,rule:null,message:null}}/>);expect(container.innerHTML).toBe("")});
  it("renders NAVI and group rules independently",()=>{render(<BettingRestrictionWarning restriction={{restricted:true,rule:"navi_no_match_winner_bets",message:"NAVI message",restrictions:[{rule:"navi_no_match_winner_bets",message:"NAVI message"},{rule:"group_stage_no_match_winner_bets",message:"НЕ СТАВИТЬ НА ПОБЕДИТЕЛЯ МАТЧА."}]}}/>);const alerts=screen.getAllByRole("alert");expect(alerts).toHaveLength(2);expect(alerts[0].textContent).toContain("NAVI RULE");expect(alerts[1].textContent).toContain("GROUP STAGE RULE")});
});
