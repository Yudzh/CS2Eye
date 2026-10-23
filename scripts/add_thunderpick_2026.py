"""Add the verified Thunderpick 2026 field and GSL/playoff bracket once.

Sources (checked 2026-10-14):
https://world-championship.thunderpick.io/2026-finals/
https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy
https://www.hltv.org/events/8932/matches
https://bo3.gg/tournaments/thunderpick-world-championship-2026
Opening times cross-checked as UTC on BO3. Later group match times are
left unset because the public schedule does not identify their GSL roles.
"""
import asyncio
from datetime import date, datetime, UTC
from sqlalchemy import select
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.team import Team

NAME = 'Thunderpick World Championship 2026'
PARTICIPANTS = ['Falcons', 'Ninjas in Pyjamas', '9z', 'Aurora', 'Legacy', 'PARIVISION', 'FURIA', 'BetBoom']


def build_matches(tournament_id, teams):
    slots = {}
    def add(key, day, label, *, group=None, round_number=1, position=1, pair=None, time=None, stage='group', format='bo3', elimination=False):
        slots[key] = Match(tournament_id=tournament_id, match_date=date(2026,10,day),
            starts_at=datetime.fromisoformat(f'2026-10-{day:02d}T{time}:00+00:00') if time else None,
            team_a_id=teams[pair[0]] if pair else None, team_b_id=teams[pair[1]] if pair else None,
            format=format, stage=stage, environment='lan', status='scheduled', resolution_status='resolved',
            round_number=round_number, round_label=label, group_name=group,
            bracket_section=('lower' if key.endswith(('e','d')) else 'upper') if group else 'main', bracket_position=position,
            is_playoff=group is None, is_elimination=elimination, team_a_maps_won=0, team_b_maps_won=0)
    add('a1',14,'Group A · Opening 2',group='A',position=2,pair=('9z','Aurora'),time='08:30')
    add('a2',14,'Group A · Opening 1',group='A',position=1,pair=('Falcons','Ninjas in Pyjamas'),time='11:00')
    add('b1',14,'Group B · Opening 1',group='B',pair=('Legacy','PARIVISION'),time='13:30')
    add('b2',14,'Group B · Opening 2',group='B',position=2,pair=('FURIA','BetBoom'),time='16:00')
    for group in ('A','B'):
        key=group.lower()
        add(key+'w',15,f'Group {group} · Winners match',group=group,round_number=2)
        add(key+'e',15,f'Group {group} · Elimination match',group=group,round_number=2,position=2,elimination=True)
        add(key+'d',16,f'Group {group} · Decider',group=group,round_number=3,elimination=True)
    add('s1',17,'Semifinal 1 · A1 vs B2',stage='semifinal',time='14:00',elimination=True)
    add('s2',17,'Semifinal 2 · B1 vs A2',stage='semifinal',position=2,time='17:00',elimination=True)
    add('third',18,'3rd place decider',stage='unknown',round_number=2,position=2,time='11:30')
    add('final',18,'Grand Final',stage='final',round_number=2,format='bo5',time='15:00',elimination=True)
    return slots


def link_bracket(slots):
    def link(source, target, slot, loser=False):
        prefix='loser_next_match' if loser else 'next_match'
        setattr(slots[source],prefix+'_id',slots[target].id)
        setattr(slots[source],prefix+'_slot',slot)
    for group in ('a','b'):
        for number,slot in ((1,'team_a'),(2,'team_b')):
            link(group+str(number),group+'w',slot)
            link(group+str(number),group+'e',slot,loser=True)
        link(group+'w',group+'d','team_a',loser=True)
        link(group+'e',group+'d','team_b')
    link('aw','s1','team_a');link('bd','s1','team_b')
    link('bw','s2','team_a');link('ad','s2','team_b')
    for key,slot in (('s1','team_a'),('s2','team_b')):
        link(key,'final',slot);link(key,'third',slot,loser=True)


async def main():
    async with AsyncSessionLocal() as session:
        existing=await session.scalar(select(Tournament).where(Tournament.name==NAME))
        if existing:
            print(f'Already exists: tournament {existing.id}; no changes')
            return
        teams={team.name:team.id for team in (await session.scalars(select(Team).where(Team.name.in_(PARTICIPANTS)))).all()}
        if set(teams)!=set(PARTICIPANTS):raise ValueError(f'Missing teams: {set(PARTICIPANTS)-set(teams)}')
        tournament=Tournament(name=NAME,year=2026,tier='S',environment='lan',start_date=date(2026,10,14),end_date=date(2026,10,18),structure_type='groups_playoff')
        session.add(tournament);await session.flush()
        session.add_all([TournamentTeam(tournament_id=tournament.id,team_id=teams[name]) for name in PARTICIPANTS])
        slots=build_matches(tournament.id,teams)
        session.add_all(slots.values());await session.flush();link_bracket(slots)
        await session.commit()
        print(f'Created tournament {tournament.id}: {len(PARTICIPANTS)} teams, {len(slots)} matches')
        for key,match in slots.items():print(key,match.id,match.round_label,match.starts_at)

if __name__=='__main__':asyncio.run(main())
