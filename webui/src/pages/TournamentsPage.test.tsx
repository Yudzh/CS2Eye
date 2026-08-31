import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {GroupBracket,PredictionCard,TournamentsPage} from "./TournamentsPage";
import type {MatchSeries,TournamentPredictionMatch,TournamentPredictions,TournamentView} from "../types";

const api=vi.hoisted(()=>({getTournamentView:vi.fn(),getTournamentPredictions:vi.fn(),generateTournamentPredictions:vi.fn()}));
vi.mock("../api",()=>({...api,captureTournamentPredictionHistory:vi.fn(),getTournaments:vi.fn(),patchMatchSeries:vi.fn(),patchTournament:vi.fn(),updateMatchVeto:vi.fn(),updateMatchVetoText:vi.fn()}));
afterEach(()=>cleanup());

const projected:TournamentPredictionMatch={id:10,source_match_id:null,round_number:2,round_label:"Semifinal",stage:"semifinal",bracket_section:"main",bracket_position:1,format:"bo3",team_a:{id:1,name:"Spirit"},team_b:{id:2,name:"Vitality"},team_a_probability:.56,team_b_probability:.44,team_a_score:null,team_b_score:null,predicted_winner_id:1,predicted_winner_name:"Spirit",confidence:.67,reliability:.67,prediction_type:"projected_match",prediction_basis:"win_probability",status:"available",model_version:"win_v1",created_at:"2026-08-25T14:30:00Z",invalidated_at:null};

describe("tournament prediction UI",()=>{
  it("renders double-elimination group rounds as connected upper/lower brackets",()=>{
    const match=(id:number,section:"upper"|"lower",round:number,position:number,a:string,b:string):MatchSeries=>({id,stage:"group",group_name:"A",bracket_section:section,round_number:round,bracket_position:position,round_label:`Group A: ${section} ${round}`,team_a:{id:id*2,name:a},team_b:{id:id*2+1,name:b},status:"scheduled",score:{team_a:0,team_b:0},winner_team_id:null,maps:[],format:"bo3",environment:"lan",match_date:"2026-08-29",resolution_status:"resolved",is_playoff:false,is_elimination:section==="lower",tournament:null,veto_data_status:"not_available",veto_expected:false,veto:[],next_match_id:null,next_match_slot:null});
    const upper1=match(1,"upper",1,1,"G2","Aurora"),upper2=match(2,"upper",1,2,"Spirit","DENDELE"),upperFinal=match(3,"upper",2,1,"G2","Spirit"),lower1=match(4,"lower",1,1,"Aurora","DENDELE"),lowerFinal=match(5,"lower",2,1,"Aurora","M80");
    const view={matches:[upper1,upper2,upperFinal,lower1,lowerFinal],bracket_links:[{from_match_id:1,to_match_id:3,source:"manual"},{from_match_id:2,to_match_id:3,source:"manual"},{from_match_id:4,to_match_id:5,source:"manual"}]} as TournamentView;
    const {container}=render(<GroupBracket view={view} group="A" onEdit={vi.fn()}/>);
    expect(screen.getByRole("region",{name:"Группа A"})).toBeTruthy();
    expect(screen.getByText("Верхняя сетка")).toBeTruthy();
    expect(screen.getByText("Нижняя сетка")).toBeTruthy();
    expect(container.querySelectorAll(".bracket-connectors path")).toHaveLength(3);
  });

  it("shows probability, winner, confidence, projected marker and Compare link",()=>{
    render(<PredictionCard match={projected}/>);
    expect(screen.getByText("56%")).toBeTruthy();
    expect(screen.getByText(/Прогноз:/).textContent).toContain("Spirit");
    expect(screen.getByText("Confidence: 67%")).toBeTruthy();
    expect(screen.getByText(/Прогнозная пара/)).toBeTruthy();
    expect(screen.getByRole("link",{name:"Сравнить команды"}).getAttribute("href")).toContain("team_a=1&team_b=2");
  });

  it("shows insufficient_data without selecting a winner",()=>{
    render(<PredictionCard match={{...projected,status:"insufficient_data",predicted_winner_id:null,predicted_winner_name:null,team_a_probability:null,team_b_probability:null,confidence:null}}/>);
    expect(screen.getByText("Недостаточно данных для прогноза")).toBeTruthy();
    expect(screen.queryByText(/Прогноз:/)).toBeNull();
  });

  it("switches actual/predicted brackets, shows outdated state and recalculates",async()=>{
    const view:TournamentView={tournament:{id:1,name:"Future Cup",year:2026,tier:"S",environment:"lan",start_date:"2026-09-01",end_date:"2026-09-03",structure_type:"single_elimination"},summary:{series_count:0,map_count:0,parsed_maps:0,review_series:0,missing_veto_series:0,participant_count:2,scheduled_series:0},matches:[],stages:[],bracket_links:[],problems:[],participants:[]};
    const prediction:TournamentPredictions={tournament_id:1,prediction_run_id:1,generated_at:"2026-08-25T14:30:00Z",model_version:"win_v1",status:"succeeded",outdated:true,matches:[projected]};
    api.getTournamentView.mockResolvedValue(view);api.getTournamentPredictions.mockResolvedValue(prediction);api.generateTournamentPredictions.mockResolvedValue({...prediction,outdated:false});
    render(<TournamentsPage tournamentId={1}/>);
    await screen.findByText("Future Cup 2026");
    fireEvent.click(screen.getByRole("button",{name:"Прогноз CS2Eye"}));
    expect(await screen.findByText(/требует пересчёта/)).toBeTruthy();
    expect(screen.getByText(/Прогнозная пара/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:"Пересчитать"}));
    await waitFor(()=>expect(api.generateTournamentPredictions).toHaveBeenCalledWith(1));
  });
});
