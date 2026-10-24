"""Populate PGL Masters Bucharest 2026 without inventing Swiss pairings.

Verified 2026-10-24:
https://www.pglesports.com/cs2/pgl-masters-bucharest-2026/
https://bo3.gg/tournaments/pgl-masters-bucharest-2026
https://www.hltv.org/events/8050/pgl-masters-bucharest-2026

All times UTC. Later Swiss starting times remain unset pending confirmation.
Swiss progression is determined by record and reseeding, never fixed links.
Run with --predict to save forecasts for known pairs using the active model.
"""
import argparse
import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select, text

from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.team import Team

NAME = 'PGL Masters Bucharest 2026'
OPENING = [
    ('Aurora', 'The MongolZ', 7), ('FUT', 'TYLOO', 7),
    ('Spirit', 'BetBoom', 10), ('MOUZ', 'Liquid', 10),
    ('Vitality', '9z', 13), ('Legacy', 'Nemiga', 13),
    ('G2', 'Natus Vincere', 16), ('FURIA', 'DENDELE', 16),
]
PARTICIPANTS = [name for a, b, _ in OPENING for name in (a, b)]
SWISS_RECORDS = {
    2: [('1-0', 4), ('0-1', 4)],
    3: [('2-0', 2), ('1-1', 4), ('0-2', 2)],
    4: [('2-1', 3), ('1-2', 3)],
    5: [('2-2', 3)],
}


def build_matches(tournament_id, teams):
    matches = {}

    def add(key, day, label, *, round_number, position=1, pair=None,
            hour=None, stage='swiss', elimination=False, format='bo3'):
        playoff = stage != 'swiss'
        matches[key] = Match(
            tournament_id=tournament_id, match_date=date(2026, 10, day),
            starts_at=datetime(2026, 10, day, hour, tzinfo=UTC) if hour is not None else None,
            team_a_id=teams[pair[0]] if pair else None,
            team_b_id=teams[pair[1]] if pair else None,
            format=format, stage=stage, environment='lan', status='scheduled',
            resolution_status='resolved', round_number=round_number,
            round_label=label, bracket_section='main' if playoff else 'swiss',
            bracket_position=position, is_playoff=playoff, is_elimination=elimination,
            team_a_maps_won=0, team_b_maps_won=0,
        )

    for index, (a, b, hour) in enumerate(OPENING, 1):
        add(f'r1-{index}', 24, f'Swiss round 1 · 0-0 · {index}',
            round_number=1, position=index, pair=(a, b), hour=hour)
    for round_number, records in SWISS_RECORDS.items():
        position = 0
        for record, count in records:
            for index in range(1, count + 1):
                position += 1
                add(f'r{round_number}-{record}-{index}', 23 + round_number,
                    f'Swiss round {round_number} · {record} · {index}',
                    round_number=round_number, position=position,
                    elimination=record.endswith('-2'))
    for index, hour in enumerate((8, 11, 14, 17), 1):
        add(f'q{index}', 29, f'Quarterfinal {index}', round_number=6,
            position=index, hour=hour, stage='quarterfinal', elimination=True)
    for index, hour in enumerate((12, 15), 1):
        add(f's{index}', 30, f'Semifinal {index}', round_number=7,
            position=index, hour=hour, stage='semifinal', elimination=True)
    add('third', 31, '3rd place decider', round_number=8, position=2,
        hour=8, stage='unknown')
    add('final', 31, 'Grand Final', round_number=8, hour=11,
        stage='final', elimination=True, format='bo5')
    return matches


def link_bracket(matches):
    # Playoff bracket slots; Swiss qualifiers are filled after seeding is announced.
    for index in range(1, 5):
        source = matches[f'q{index}']
        source.next_match_id = matches[f's{(index + 1) // 2}'].id
        source.next_match_slot = 'team_a' if index % 2 else 'team_b'
    for index, slot in ((1, 'team_a'), (2, 'team_b')):
        source = matches[f's{index}']
        source.next_match_id, source.next_match_slot = matches['final'].id, slot
        source.loser_next_match_id, source.loser_next_match_slot = matches['third'].id, slot


async def populate():
    async with AsyncSessionLocal() as session:
        await session.execute(text('SELECT pg_advisory_xact_lock(2026, 8050)'))
        tournament = await session.scalar(select(Tournament).where(
            Tournament.name == NAME, Tournament.year == 2026))
        if tournament and await session.scalar(select(Match.id).where(
                Match.tournament_id == tournament.id).limit(1)):
            print(f'Already populated: tournament {tournament.id}; existing data preserved')
            return tournament.id
        teams = {team.name: team.id for team in (await session.scalars(
            select(Team).where(Team.name.in_(PARTICIPANTS)))).all()}
        missing = set(PARTICIPANTS) - teams.keys()
        if missing:
            raise ValueError(f'Missing teams (import from BO3 first): {sorted(missing)}')
        if tournament is None:
            tournament = Tournament(name=NAME, year=2026)
            session.add(tournament)
        tournament.tier, tournament.environment = 'S', 'lan'
        tournament.start_date, tournament.end_date = date(2026, 10, 24), date(2026, 10, 31)
        tournament.structure_type = 'swiss'
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
        print(f'Populated tournament {tournament.id}: 16 teams, {len(matches)} matches')
        return tournament.id


async def main(predict=False):
    tournament_id = await populate()
    if predict:
        from cs2eye.services.prediction_history_service import PredictionHistoryService
        async with AsyncSessionLocal() as session:
            result = await PredictionHistoryService(session).capture_tournament(tournament_id)
            await session.commit()
            print(f'Forecast capture: {result}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predict', action='store_true')
    asyncio.run(main(parser.parse_args().predict))
