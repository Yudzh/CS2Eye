import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {PandaScoreRosterPanel} from "./PandaScoreRosterPanel";
import {getPandaScoreRoster,refreshPandaScoreRoster,selectPandaScoreRoster} from "../api";
vi.mock("../api",()=>({getPandaScoreRoster:vi.fn(),refreshPandaScoreRoster:vi.fn(),selectPandaScoreRoster:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const six={players:Array.from({length:6},(_,i)=>({id:i+1,name:`Player ${i+1}`,slug:`p${i+1}`,nationality:"RU"})),checked_at:"2026-10-26T00:00:00Z",source:"PandaScore",status:"needs_review",selected_ids:[]};
it("requires an explicit five-player selection from a six-player list",async()=>{
 vi.mocked(getPandaScoreRoster).mockResolvedValue(null);
 vi.mocked(refreshPandaScoreRoster).mockResolvedValue(six);
 vi.mocked(selectPandaScoreRoster).mockResolvedValue({...six,status:"saved",selected_ids:[1,2,3,4,5]});
 const saved=vi.fn().mockResolvedValue(undefined);
 render(<PandaScoreRosterPanel teamId={9} onSaved={saved}/>);
 fireEvent.click(screen.getByText("Получить состав из PandaScore"));
 await screen.findByText(/Player 6/);
 expect(selectPandaScoreRoster).not.toHaveBeenCalled();
 expect(screen.getByRole("button",{name:/Сохранить основную пятёрку/}).hasAttribute("disabled")).toBe(true);
 screen.getAllByRole("checkbox").slice(0,5).forEach(c=>fireEvent.click(c));
 fireEvent.click(screen.getByRole("button",{name:/Сохранить основную пятёрку/}));
 await waitFor(()=>expect(selectPandaScoreRoster).toHaveBeenCalledWith(9,[1,2,3,4,5]));
 await waitFor(()=>expect(saved).toHaveBeenCalledOnce());
});
it("keeps incomplete provider lists out of the current roster",async()=>{
 vi.mocked(getPandaScoreRoster).mockResolvedValue({...six,players:six.players.slice(0,4),status:"partial"});
 render(<PandaScoreRosterPanel teamId={9} onSaved={vi.fn()}/>);
 await screen.findByText(/Источник вернул неполный состав/);
 expect(screen.getByRole("button",{name:/Сохранить основную пятёрку/}).hasAttribute("disabled")).toBe(true);
 expect(selectPandaScoreRoster).not.toHaveBeenCalled();
});
