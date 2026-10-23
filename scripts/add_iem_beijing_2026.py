"""Populate IEM Beijing 2026; safe to rerun, never replace existing matches.

Verified 2026-10-21:
https://pro.eslgaming.com/tour/cs/beijing/
https://www.hltv.org/news/45759/iem-beijing-groups-and-opening-matchups-set
https://www.hltv.org/events/8245/matches

Group round dates follow the three-day, eight-series-per-day format.
Opening times remain unset: HLTV currently gives the same time to all eight.
Playoff times are converted from the official Beijing (UTC+8) schedule.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text

from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.team import Team

NAME = 'IEM Beijing 2026'
GROUPS = {
    'A': [('Natus Vincere', 'Falcons'), ('FURIA', 'FaZe'),
          ('HEROIC', 'B8'), ('Legacy', 'The MongolZ')],
    'B': [('G2', 'PARIVISION'), ('BetBoom', '9z'),
          ('Aurora', 'Liquid'), ('MOUZ', 'TYLOO')],
}
PARTICIPANTS = [name for pairs in GROUPS.values() for pair in pairs for name in pair]


def build_matches(tournament_id, teams):
    matches = {}

    def add(key, day, label, *, group=None, section='upper', round_number=1,
            position=1, pair=None, stage='group', time=None, format='bo3'):
        starts_at = None
        if time:
            starts_at = datetime.fromisoformat(f'2026-11-{day:02d}T{time}:00').replace(
                tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
        matches[key] = Match(
            tournament_id=tournament_id, match_date=date(2026, 11, day), starts_at=starts_at,
            team_a_id=teams[pair[0]] if pair else None,
            team_b_id=teams[pair[1]] if pair else None,
            format=format, stage=stage, environment='lan', status='scheduled',
            resolution_status='resolved', round_number=round_number, round_label=label,
            group_name=group, bracket_section=section if group else 'main',
            bracket_position=position, is_playoff=group is None,
            is_elimination=section == 'lower' or (group is None and key != 'third'),
            team_a_maps_won=0, team_b_maps_won=0,
        )

    for group, pairs in GROUPS.items():
        for index, pair in enumerate(pairs, 1):
            add(f'{group}u{index}', 2, f'Group {group} · Upper quarterfinal {index}',
                group=group, position=index, pair=pair)
        for index in (1, 2):
            add(f'{group}s{index}', 3, f'Group {group} · Upper semifinal {index}',
                group=group, round_number=2, position=index)
            add(f'{group}l{index}', 3, f'Group {group} · Lower round 1 · {index}',
                group=group, section='lower', position=index)
            add(f'{group}d{index}', 4, f'Group {group} · Lower semifinal {index}',
                group=group, section='lower', round_number=2, position=index)
        add(f'{group}uf', 4, f'Group {group} · Upper final', group=group, round_number=3)
        add(f'{group}lf', 4, f'Group {group} · Lower final', group=group,
            section='lower', round_number=3)
    for index, time in ((1, '14:30'), (2, '17:45')):
        add(f'q{index}', 6, f'Quarterfinal {index}', stage='quarterfinal', position=index, time=time)
        add(f's{index}', 7, f'Semifinal {index}', stage='semifinal', round_number=2,
            position=index, time=time)
    add('third', 8, '3rd place decider', stage='unknown', round_number=3, position=2, time='12:00')
    add('final', 8, 'Grand Final', stage='final', round_number=3, time='15:30', format='bo5')
    return matches


def link_bracket(matches):
    def link(source, target, slot, loser=False):
        prefix = 'loser_next_match' if loser else 'next_match'
        setattr(matches[source], prefix + '_id', matches[target].id)
        setattr(matches[source], prefix + '_slot', slot)

    for group in GROUPS:
        for index in range(1, 5):
            half = (index + 1) // 2
            slot = 'team_a' if index % 2 else 'team_b'
            link(f'{group}u{index}', f'{group}s{half}', slot)
            link(f'{group}u{index}', f'{group}l{half}', slot, loser=True)
        for index, slot in ((1, 'team_a'), (2, 'team_b')):
            link(f'{group}s{index}', f'{group}uf', slot)
            # Lower bracket crosses over to avoid an immediate rematch.
            link(f'{group}s{index}', f'{group}d{3-index}', 'team_a', loser=True)
            link(f'{group}l{index}', f'{group}d{index}', 'team_b')
            link(f'{group}d{index}', f'{group}lf', slot)
    # Group winners meet the opposite side's quarterfinal winner.
    link('Auf', 's1', 'team_a'); link('Buf', 's2', 'team_a')
    link('Auf', 'q2', 'team_a', loser=True); link('Blf', 'q2', 'team_b')
    link('Buf', 'q1', 'team_a', loser=True); link('Alf', 'q1', 'team_b')
    for index, slot in ((1, 'team_a'), (2, 'team_b')):
        link(f'q{index}', f's{index}', 'team_b')
        link(f's{index}', 'final', slot)
        link(f's{index}', 'third', slot, loser=True)


async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(text('SELECT pg_advisory_xact_lock(2026, 8245)'))
        tournament = await session.scalar(select(Tournament).where(
            Tournament.name == NAME, Tournament.year == 2026))
        if tournament and await session.scalar(select(Match.id).where(
                Match.tournament_id == tournament.id).limit(1)):
            print(f'Already populated: tournament {tournament.id}; no changes')
            return
        teams = {team.name: team.id for team in (await session.scalars(
            select(Team).where(Team.name.in_(PARTICIPANTS)))).all()}
        missing = set(PARTICIPANTS) - teams.keys()
        if missing:
            raise ValueError(f'Missing teams: {sorted(missing)}')
        if tournament is None:
            tournament = Tournament(name=NAME, year=2026)
            session.add(tournament)
        tournament.tier = 'S'
        tournament.environment = 'lan'
        tournament.start_date = date(2026, 11, 2)
        tournament.end_date = date(2026, 11, 8)
        tournament.structure_type = 'groups_playoff'
        await session.flush()
        existing = set((await session.scalars(select(TournamentTeam.team_id).where(
            TournamentTeam.tournament_id == tournament.id))).all())
        session.add_all([TournamentTeam(tournament_id=tournament.id, team_id=teams[name])
                         for name in PARTICIPANTS if teams[name] not in existing])
        matches = build_matches(tournament.id, teams)
        session.add_all(matches.values())
        await session.flush()
        link_bracket(matches)
        await session.commit()
        print(f'Populated tournament {tournament.id}: {len(PARTICIPANTS)} teams, {len(matches)} matches')


if __name__ == '__main__':
    asyncio.run(main())
