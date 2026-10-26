"""Repair verified BO3/PandaScore player identities without rewriting archived forecasts."""
from sqlalchemy import select
from cs2eye.models.team import Player,Team,TeamRoster,TeamRosterMember,TeamParticipantMembership
from cs2eye.models.match import TournamentRosterCheck
from cs2eye.deployment.pandascore_replacements import apply as reconcile_replacements


def profile_key(first,last,country):
    if not first or not last or not country:
        return None
    parts=tuple(sorted((' '.join(first.split()).casefold(),' '.join(last.split()).casefold())))
    return (country.upper(),parts) if all(len(p)>1 for p in parts) else None


def apply(session):
    # Explicitly verified: BO3 Techno4K and PandaScore Techno are Sodbayar Munkhbold (MN).
    canonical=session.scalar(select(Player).where(Player.bo3_id==29449))
    provider=session.scalar(select(Player).where(Player.pandascore_id==30001))
    if provider is None:
        return {'repaired':0}
    if canonical is None:
        raise ValueError('Techno identity repair requires the recorded BO3 player 29449.')
    if canonical.id==provider.id:
        return {'repaired':0}
    expected=('MN',('munkhbold','sodbayar'))
    if profile_key(canonical.first_name,canonical.last_name,canonical.country_code)!=expected or profile_key(provider.first_name,provider.last_name,provider.country_code)!=expected:
        raise ValueError('Techno identity repair requires matching verified full names and nationality.')
    if canonical.pandascore_id is not None or provider.bo3_id is not None:
        raise ValueError('Techno identity repair found conflicting provider identities.')
    external_id,slug=provider.pandascore_id,provider.pandascore_slug
    provider.pandascore_id=None
    provider.pandascore_slug=None
    session.flush()  # release the unique provider identity before assigning it
    canonical.pandascore_id=external_id
    canonical.pandascore_slug=slug
    canonical.is_analytics_active = canonical.is_analytics_active or provider.is_analytics_active
    # Correct current event identity references while retaining original observation timestamps.
    for capture in session.scalars(select(TournamentRosterCheck).where(
        TournamentRosterCheck.source.like('https://api.pandascore.co/%'))).all():
        def replace(ids):
            return sorted({canonical.id if pid==provider.id else pid for pid in (ids or [])})
        if provider.id in (capture.roster_ids or []) or provider.id in capture.baseline_ids:
            capture.roster_ids=replace(capture.roster_ids)
            capture.baseline_ids=replace(capture.baseline_ids)
            if len(capture.roster_ids)!=5:
                raise ValueError('Identity repair would collapse the event roster below five players.')
            capture.added_ids=sorted(set(capture.roster_ids)-set(capture.baseline_ids))
            capture.missing_ids=sorted(set(capture.baseline_ids)-set(capture.roster_ids))
            if capture.status in {"changed","unchanged"}:
                capture.status="changed" if capture.added_ids or capture.missing_ids else "unchanged"
    for team in session.scalars(select(Team).where(Team.current_roster_id.is_not(None))).all():
        old=session.get(TeamRoster,team.current_roster_id)
        members=list(session.scalars(select(TeamRosterMember).where(TeamRosterMember.roster_id==old.id)).all())
        if not any(m.player_id==provider.id for m in members):
            continue
        ids=sorted({canonical.id if m.player_id==provider.id else m.player_id for m in members})
        if len(ids)!=5 or None in ids:
            raise ValueError('Identity repair would collapse the main roster below five players.')
        from cs2eye.services.team_roster_service import build_roster_fingerprint
        fingerprint=build_roster_fingerprint(ids)
        replacement=session.scalar(select(TeamRoster).where(TeamRoster.team_id==team.id,TeamRoster.fingerprint==fingerprint))
        old.is_current=False
        session.flush()
        if replacement is None:
            replacement=TeamRoster(team_id=team.id,fingerprint=fingerprint,source=old.source,
                resolution_status='complete',is_current=False,active_from=old.active_from,
                active_from_source=old.active_from_source)
            session.add(replacement);session.flush()
            by_id={p.id:p for p in session.scalars(select(Player).where(Player.id.in_(ids))).all()}
            for member in members:
                player_id=canonical.id if member.player_id==provider.id else member.player_id
                player=by_id[player_id]
                session.add(TeamRosterMember(roster_id=replacement.id,player_id=player_id,
                    player_name_snapshot=player.nickname,role_snapshot=member.role_snapshot,
                    player_external_id=player.steam_id or (f'pandascore:{player.pandascore_id}' if player.pandascore_id else str(player.bo3_id))))
        replacement.is_current=True
        team.current_roster_id=replacement.id
        for membership in session.scalars(select(TeamParticipantMembership).where(
            TeamParticipantMembership.team_id==team.id,TeamParticipantMembership.player_id==provider.id,
            TeamParticipantMembership.is_active.is_(True))).all():
            membership.is_active=False
        existing=session.scalar(select(TeamParticipantMembership).where(
            TeamParticipantMembership.team_id==team.id,TeamParticipantMembership.player_id==canonical.id,
            TeamParticipantMembership.is_active.is_(True)))
        if existing is None:
            session.add(TeamParticipantMembership(team_id=team.id,player_id=canonical.id,participant_type='player'))
        team.team_strength_v3_breakdown=None
        team.team_strength_v3_calculated_at=None
    # Keep the old local player and historical roster rows: existing archived references stay valid.
    session.flush()
    reconcile_replacements(session)
    return {'repaired':1}
