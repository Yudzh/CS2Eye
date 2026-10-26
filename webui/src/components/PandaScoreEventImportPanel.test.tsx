import '@testing-library/jest-dom/vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {PandaScoreEventImportPanel} from './PandaScoreEventImportPanel';
const api=vi.hoisted(()=>({searchPandaScoreEvents:vi.fn(),importPandaScoreEvent:vi.fn()}));
vi.mock('../api',()=>api);
afterEach(()=>{cleanup();vi.resetAllMocks()});
it('finds a named event, imports selected identity and explains incomplete brackets',async()=>{
 api.searchPandaScoreEvents.mockResolvedValue([{id:11136,name:'IEM Beijing 2026',year:2026,begin_at:'2026-11-02',end_at:'2026-11-08',stages:[{id:22267,name:'Group A'}]}]);
 api.importPandaScoreEvent.mockResolvedValue({id:30,name:'IEM Beijing 2026',teams:16,matches:8,warnings:['Group A: связи сетки пока отсутствуют.']});
 const reload=vi.fn().mockResolvedValue(undefined);
 render(<PandaScoreEventImportPanel onImported={reload}/>);
 fireEvent.change(screen.getByLabelText('Название турнира'),{target:{value:'IEM Beijing 2026'}});
 fireEvent.click(screen.getByRole('button',{name:'Найти турнир'}));
 fireEvent.click(await screen.findByRole('button',{name:'Добавить / обновить турнир'}));
 await waitFor(()=>expect(api.importPandaScoreEvent).toHaveBeenCalledWith(11136));
 expect(await screen.findByRole('link',{name:'IEM Beijing 2026'})).toHaveAttribute('href','/tournaments/30');
 expect(screen.getByText('Group A: связи сетки пока отсутствуют.')).toBeTruthy();
 expect(reload).toHaveBeenCalledTimes(1);
});
it('shows provider errors and permits retry',async()=>{
 api.searchPandaScoreEvents.mockRejectedValue(new Error('PandaScore недоступен'));
 render(<PandaScoreEventImportPanel onImported={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText('Название турнира'),{target:{value:'Beijing'}});
 fireEvent.click(screen.getByRole('button',{name:'Найти турнир'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('PandaScore недоступен');
 expect(screen.getByRole('button',{name:'Найти турнир'})).not.toBeDisabled();
});
