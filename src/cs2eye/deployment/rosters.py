"""Release checks for configured PandaScore roster identities, without network writes."""
from sqlalchemy import select
from cs2eye.models.team import Team, Player, TeamRosterMember
from cs2eye.models.match import TournamentRosterCheck


async def verify_rosters(factory):
    report = {'main':0, 'tournament':0, 'errors':[]}
    async with factory() as session:
        teams = list((await session.scalars(select(Team).where(Team.pandascore_roster_synced_at.is_not(None)))).all())
        for team in teams:
            selected = (team.pandascore_roster_data or {}).get('selected_ids', [])
            provider_ids = list((await session.scalars(select(Player.pandascore_id).join(
                TeamRosterMember, TeamRosterMember.player_id == Player.id).where(
                    TeamRosterMember.roster_id == team.current_roster_id))).all())
            if len(provider_ids) != 5 or None in provider_ids or len(set(provider_ids)) != 5 or set(provider_ids) != set(selected):
                report['errors'].append(f'Team {team.id}: saved PandaScore roster identities disagree')
            report['main'] += 1
        captures = list((await session.scalars(select(TournamentRosterCheck).where(
            TournamentRosterCheck.source.like('https://api.pandascore.co/%')))).all())
        for capture in captures:
            ids = capture.roster_ids or []
            provider_ids = list((await session.scalars(select(Player.pandascore_id).where(Player.id.in_(ids)))).all())
            if (len(ids) != 5 or len(set(ids)) != 5 or len(provider_ids) != 5 or None in provider_ids
                    or len(set(provider_ids)) != 5 or capture.checked_at is None):
                report['errors'].append(f'Tournament {capture.tournament_id}, team {capture.team_id}: incomplete PandaScore roster')
            report['tournament'] += 1
    return report
