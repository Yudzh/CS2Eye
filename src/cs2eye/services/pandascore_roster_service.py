"""PandaScore team lists and event snapshots, without guessing reserve roles."""
from datetime import UTC, datetime, timedelta, time
import unicodedata

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from cs2eye.core.config import settings
from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.team import Player, Team, TeamParticipantMembership
from cs2eye.models.match import Match, Tournament, TournamentTeam, TournamentRosterCheck, TournamentRosterOverride
from cs2eye.services.match_result_sync_service import MatchResultSyncService, normalized
from cs2eye.services.team_roster_service import set_current_roster, get_or_create_roster


def nickname_key(value):
    return unicodedata.normalize("NFC", value.strip()).casefold()


class RosterPlayer(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=160)
    nationality: str | None = Field(default=None, max_length=8)
    first_name: str | None = Field(default=None, max_length=160)
    last_name: str | None = Field(default=None, max_length=160)
    image_url: str | None = None


def roster_players(row):
    try:
        players = [RosterPlayer.model_validate(item) for item in row['players']]
        if len({p.id for p in players}) != len(players):
            raise ValueError('Duplicate players')
        return players
    except (KeyError, TypeError, ValueError, ValidationError):
        raise PandaScoreError('PandaScore: некорректный или повторяющийся список игроков.') from None


class PandaScoreRosterService:
    def __init__(self, session, client_factory=PandaScoreClient):
        self.session = session
        self.client_factory = client_factory

    async def fetch(self, operation):
        if not settings.pandascore_api_token.get_secret_value():
            raise PandaScoreError('На сервере не настроен PANDASCORE_API_TOKEN.')
        sync = MatchResultSyncService(self.session)
        async with sync.locked():
            quota = await sync.quota()
            client = self.client_factory(quota, lambda: sync.reserve(quota))
            try:
                return await operation(client)
            except PandaScoreError:
                await self.session.commit()  # retain consumed quota and provider backoff
                raise
            finally:
                await client.close()

    async def resolve_players(self, items):
        """Prefer stable IDs. Only a unique exact nickname + compatible country may bootstrap a link."""
        all_players = list((await self.session.scalars(select(Player).with_for_update())).all())
        result = []
        for item in items:
            player = next((p for p in all_players if p.pandascore_id == item.id), None)
            if player is None:
                matches = [p for p in all_players if nickname_key(p.nickname) == nickname_key(item.name)]
                if matches:
                    if (len(matches) != 1 or matches[0].pandascore_id is not None or
                        (matches[0].country_code and item.nationality and matches[0].country_code != item.nationality)):
                        raise ValueError(f'Неоднозначная привязка игрока {item.name}; требуется сверка профилей.')
                    player = matches[0]
                else:
                    player = Player(nickname=item.name, is_analytics_active=False)
                    self.session.add(player)
                    all_players.append(player)
            player.pandascore_id = item.id
            player.pandascore_slug = item.slug
            # Existing BO3 profiles retain their names, ratings, photos and Steam links.
            if player.bo3_id is None:
                player.nickname = item.name
                player.first_name = item.first_name
                player.last_name = item.last_name
                player.country_code = item.nationality
                if item.image_url and item.image_url.startswith('https://'):
                    player.image_url = item.image_url
            result.append(player)
        await self.session.flush()
        if len({p.id for p in result}) != len(items):
            raise ValueError('Несколько PandaScore игроков сопоставлены одному локальному игроку.')
        return result

    async def refresh_main(self, team_id):
        team = await self.session.get(Team, team_id)
        if team is None or not team.pandascore_id:
            raise ValueError('Сначала привяжите команду к PandaScore.')
        external_id = team.pandascore_id
        rows = await self.fetch(lambda c: c.teams(**{'filter[id]': external_id}))
        if len(rows) != 1 or rows[0].get('id') != external_id:
            raise ValueError('Команда не найдена в PandaScore.')
        items = roster_players(rows[0])
        team = await self.session.scalar(select(Team).where(Team.id == team_id).with_for_update().execution_options(populate_existing=True))
        if team.pandascore_id != external_id:
            raise ValueError('Привязка команды изменилась; повторите запрос.')
        previous = team.pandascore_roster_data or {}
        snapshot = {'players':[p.model_dump() for p in items], 'checked_at':datetime.now(UTC).isoformat(),
                    'source':f'https://api.pandascore.co/csgo/teams?filter[id]={external_id}',
                    'status':'needs_review' if len(items) > 5 else 'partial',
                    'selected_ids':previous.get('selected_ids', [])}
        team.pandascore_roster_data = snapshot
        if len(items) == 5:
            await self.apply_main(team_id, [p.id for p in items])
        return team.pandascore_roster_data

    async def apply_main(self, team_id, external_ids):
        team = await self.session.scalar(select(Team).where(Team.id == team_id).with_for_update())
        if not team or not team.pandascore_roster_data:
            raise ValueError('Сначала получите список игроков PandaScore.')
        snapshot = team.pandascore_roster_data
        available = {p['id']: RosterPlayer.model_validate(p) for p in snapshot['players']}
        if len(external_ids) != 5 or len(set(external_ids)) != 5 or not set(external_ids) <= available.keys():
            raise ValueError('Выберите ровно пять разных игроков из полученного списка.')
        # Identity linking and membership changes succeed or fail together.
        async with self.session.begin_nested():
            players = await self.resolve_players([available[i] for i in external_ids])
            memberships = list((await self.session.scalars(select(TeamParticipantMembership).where(
                TeamParticipantMembership.team_id == team.id, TeamParticipantMembership.is_active.is_(True)))).all())
            selected = {p.id for p in players}
            for member in memberships:
                if member.participant_type == 'player' and member.player_id not in selected:
                    member.is_active = False
            for player in players:
                member = next((m for m in memberships if m.player_id == player.id), None)
                if member is None:
                    self.session.add(TeamParticipantMembership(team_id=team.id, player_id=player.id, participant_type='player'))
                else:
                    member.participant_type = 'player'
                player.is_analytics_active = team.is_analytics_active
            await self.session.flush()
            await set_current_roster(self.session, team.id, players, source='pandascore',
                active_from=datetime.now(UTC).date(), active_from_source='observed')
            team.pandascore_roster_synced_at = datetime.now(UTC)
            team.roster_synced_at = team.pandascore_roster_synced_at
            team.pandascore_roster_data = {**snapshot, 'status':'saved', 'selected_ids':external_ids}
            team.team_strength_v3_breakdown = None
            team.team_strength_v3_calculated_at = None
        return team.pandascore_roster_data

    async def tournament_external_id(self, tournament):
        if tournament.pandascore_id:
            return tournament.pandascore_id
        matches = list((await self.session.scalars(select(Match).where(Match.tournament_id == tournament.id))).all())
        ids = {(m.result_link or {}).get('_pandascore', {}).get('tournament', {}).get('id') for m in matches}
        ids.discard(None)
        return next(iter(ids)) if len(ids) == 1 else None

    async def discover_tournament(self, tournament_id, team_id, match_id=None):
        tournament = await self.session.get(Tournament, tournament_id)
        if tournament is None:
            raise ValueError('Турнир не найден.')
        matches = list((await self.session.scalars(select(Match).where(
            Match.tournament_id == tournament_id,
            (Match.team_a_id == team_id) | (Match.team_b_id == team_id)))).all())
        if match_id is not None:
            matches = [m for m in matches if m.id == match_id]
        if not matches:
            raise ValueError('Для поиска турнира PandaScore нужна известная пара команд в матче.')
        today = datetime.now(UTC).date()
        anchor = min(matches, key=lambda m: (abs((m.match_date - today).days), m.id))
        teams = list((await self.session.scalars(select(Team).where(
            Team.id.in_([anchor.team_a_id, anchor.team_b_id])))).all())
        if len(teams) != 2 or any(not t.pandascore_id for t in teams):
            raise ValueError('Для поиска турнира привяжите обе команды матча к PandaScore в их карточках.')
        provider_ids = {t.pandascore_id for t in teams}
        event_name, event_year = normalized(tournament.name), tournament.year
        known_match_id = anchor.result_external_id
        begin = datetime.combine(anchor.match_date, time.min, UTC) - timedelta(days=1)
        end = begin + timedelta(days=3)
        async def find(client):
            rows = []
            for kind in ('upcoming', 'running', 'past'):
                rows.extend(await client.matches(kind, **{'range[begin_at]': f'{begin.isoformat()},{end.isoformat()}'}))
            return rows
        rows = await self.fetch(find)
        candidates = {}
        for row in rows:
            league, serie = row.get('league') or {}, row.get('serie') or {}
            event_names = {normalized(' '.join(str(v or '') for v in (league.get('name'), serie.get(key))))
                           for key in ('name', 'full_name')}
            opponents = row.get('opponents') or []
            ids = {(o.get('opponent') or {}).get('id') for o in opponents if o.get('type') == 'Team'}
            if (serie.get('year') != event_year or event_name not in event_names or ids != provider_ids
                    or (known_match_id is not None and row.get('id') != known_match_id)):
                continue
            stage_id = (row.get('tournament') or {}).get('id')
            if isinstance(stage_id, int) and stage_id > 0:
                candidates[stage_id] = row
        if len(candidates) != 1:
            if candidates:
                raise ValueError('PandaScore вернул несколько стадий для этого матча; автоматический выбор неоднозначен.')
            raise ValueError('Матч с этой парой команд и турниром пока не найден в PandaScore. Повторите получение состава позже.')
        external_id = next(iter(candidates))
        await self.bind_tournament(tournament_id, external_id)
        # Persist the discovered identity before independently saving each participant's roster.
        await self.session.commit()
        return external_id

    async def bind_tournament(self, tournament_id, external_id):
        row = await self.fetch(lambda c: c.tournament(external_id))
        tournament = await self.session.scalar(select(Tournament).where(Tournament.id == tournament_id).with_for_update())
        if tournament is None:
            raise ValueError('Турнир не найден.')
        if not isinstance(row, dict) or row.get('id') != external_id or (row.get('serie') or {}).get('year') != tournament.year:
            raise ValueError('PandaScore: не найден турнир соответствующего года.')
        if (row.get('videogame') or {}).get('slug') not in {None, 'cs-go'}:
            raise ValueError('Турнир PandaScore относится к другой игре.')
        if tournament.pandascore_id and tournament.pandascore_id != external_id:
            raise ValueError('Турнир уже привязан к другой стадии PandaScore.')
        duplicate = await self.session.scalar(select(Tournament.id).where(Tournament.pandascore_id == external_id, Tournament.id != tournament_id))
        if duplicate:
            raise ValueError('Стадия PandaScore уже привязана к другому турниру.')
        tournament.pandascore_id = external_id
        tournament.pandascore_data = {k:row.get(k) for k in ['id','name','league','serie']}
        await self.session.flush()
        return tournament.pandascore_data

    async def refresh_tournament(self, tournament_id, team_id, match_id=None):
        tournament = await self.session.get(Tournament, tournament_id)
        team = await self.session.get(Team, team_id)
        participant = await self.session.scalar(select(TournamentTeam.id).where(
            TournamentTeam.tournament_id == tournament_id, TournamentTeam.team_id == team_id))
        if not tournament or not team or not participant:
            raise ValueError('Команда не является участником турнира.')
        capture = await self.session.scalar(select(TournamentRosterCheck).where(
            TournamentRosterCheck.tournament_id == tournament_id, TournamentRosterCheck.team_id == team_id))
        # Return the event snapshot even if provider configuration is temporarily unavailable.
        if capture and capture.roster_ids and 'api.pandascore.co/' in capture.source:
            return {'status':capture.status, 'source':capture.source, 'created':0}
        if not team.pandascore_id:
            raise ValueError('Сначала привяжите команду к PandaScore в её карточке.')
        external_id = await self.tournament_external_id(tournament)
        if not external_id:
            external_id = await self.discover_tournament(tournament_id, team_id, match_id)
        rows = await self.fetch(lambda c: c.tournament_rosters(external_id))
        candidates = [r for r in rows if isinstance(r, dict) and r.get('id') == team.pandascore_id]
        if len(candidates) != 1:
            raise ValueError('Команда отсутствует в составе выбранного турнира PandaScore.')
        items = roster_players(candidates[0])
        if len(items) != 5:
            raise ValueError(f'В турнирном составе PandaScore {len(items)} игроков; требуется ровно пять.')
        await self.session.scalar(select(Tournament).where(Tournament.id == tournament_id).with_for_update())
        capture = await self.session.scalar(select(TournamentRosterCheck).where(
            TournamentRosterCheck.tournament_id == tournament_id, TournamentRosterCheck.team_id == team_id).execution_options(populate_existing=True))
        if capture and capture.roster_ids and 'api.pandascore.co/' in capture.source:
            return {'status':capture.status, 'source':capture.source, 'created':0}
        from cs2eye.services.effective_roster_service import EffectiveRosterService
        baseline = await EffectiveRosterService(self.session).get_effective_roster(team_id, None)
        players = await self.resolve_players(items)
        await get_or_create_roster(self.session, team_id, players, source='tournament')
        baseline_ids = [p['id'] for p in baseline['permanent_roster']]
        if capture is None:
            capture = TournamentRosterCheck(tournament_id=tournament_id, team_id=team_id, baseline_ids=baseline_ids, source=f'https://api.pandascore.co/tournaments/{external_id}/rosters')
            self.session.add(capture)
        capture.baseline_ids = baseline_ids
        capture.roster_ids = sorted(p.id for p in players)
        capture.added_ids = sorted(set(capture.roster_ids) - set(baseline_ids))
        capture.missing_ids = sorted(set(baseline_ids) - set(capture.roster_ids))
        manual = await self.session.scalar(select(TournamentRosterOverride.id).where(
            TournamentRosterOverride.tournament_id == tournament_id, TournamentRosterOverride.team_id == team_id,
            TournamentRosterOverride.is_active.is_(True), TournamentRosterOverride.status == 'MANUAL'))
        capture.status = 'conflict' if manual else 'changed' if capture.added_ids or capture.missing_ids else 'unchanged'
        capture.source = f'https://api.pandascore.co/tournaments/{external_id}/rosters'
        capture.checked_at = datetime.now(UTC)
        capture.error = None
        from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
        await invalidate_tournament_predictions(self.session, tournament_id)
        await self.session.flush()
        return {'status':capture.status, 'source':capture.source, 'created':1}

    async def refresh_due_main(self):
        now = datetime.now(UTC)
        teams = list((await self.session.scalars(select(Team).where(Team.pandascore_id.is_not(None)))).all())
        due = [(team.id, (team.pandascore_roster_data or {}).get('checked_at')) for team in teams]
        for team_id, stamp in due:
            if stamp and datetime.fromisoformat(stamp) > now - timedelta(hours=6):
                continue
            try:
                await self.refresh_main(team_id)
                await self.session.commit()
            except (ValueError, PandaScoreError):
                await self.session.rollback()


async def find_unlinked_pandascore_player(session, nickname, country):
    candidates = [p for p in (await session.scalars(select(Player).where(
        Player.bo3_id.is_(None), Player.pandascore_id.is_not(None)))).all()
        if nickname_key(p.nickname) == nickname_key(nickname)]
    if len(candidates) == 1 and (not country or not candidates[0].country_code or candidates[0].country_code == country):
        return candidates[0]
    if candidates:
        raise ValueError(f'Неоднозначная привязка BO3 игрока {nickname} к PandaScore.')
    return None
