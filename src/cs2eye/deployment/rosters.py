"""Release checks for configured PandaScore roster identities, without network writes."""
from datetime import UTC, datetime
from sqlalchemy import select
from cs2eye.models.team import Team, Player, TeamRosterMember, AnalystFactor
from cs2eye.models.match import TournamentRosterCheck, TournamentRosterOverride, Tournament


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
            tournament = await session.get(Tournament, capture.tournament_id)
            today = datetime.now(UTC).date()
            if tournament and tournament.start_date and tournament.end_date and tournament.start_date <= today <= tournament.end_date:
                team = await session.get(Team, capture.team_id)
                main_ids = set((await session.scalars(select(TeamRosterMember.player_id).where(
                    TeamRosterMember.roster_id == team.current_roster_id))).all()) if team else set()
                overrides = list((await session.scalars(select(TournamentRosterOverride).where(
                    TournamentRosterOverride.tournament_id == capture.tournament_id,
                    TournamentRosterOverride.team_id == capture.team_id))).all())
                from cs2eye.deployment.pandascore_replacements import POLICY
                active = [r for r in overrides if r.is_active and (not r.valid_from or r.valid_from <= today)
                          and (not r.valid_until or r.valid_until >= today)]
                manual = any(r.status == 'MANUAL' for r in active)
                rejected = {(r.player_out_id,r.player_in_id) for r in overrides if r.notes == POLICY and r.status == 'REJECTED'}
                generated = [r for r in active if r.notes == POLICY and r.status == 'CONFIRMED']
                if len(main_ids) == 5 and None not in main_ids:
                    expected = set(zip(sorted(main_ids-set(ids)),sorted(set(ids)-main_ids))) - rejected if not manual else set()
                    if {(r.player_out_id,r.player_in_id) for r in generated} != expected:
                        report['errors'].append(f'Tournament {capture.tournament_id}, team {capture.team_id}: replacement comparison is not prepared')
                    for row in generated:
                        factor = await session.get(AnalystFactor,row.analyst_factor_id) if row.analyst_factor_id else None
                        if not factor or not factor.is_active:
                            report['errors'].append(f'Replacement {row.id}: analytical factor is unavailable')
            report['tournament'] += 1
    return report
