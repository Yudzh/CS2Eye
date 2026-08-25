from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.match import Match, Tournament
from cs2eye.services.match_service import MatchService, MatchView


PLAYOFF_STAGES = ("round_of_32", "round_of_16", "quarterfinal", "semifinal", "final")
STAGE_ORDER = {stage: index for index, stage in enumerate(PLAYOFF_STAGES)}


class TournamentNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class TournamentProblemItem:
    match_id: int
    code: str
    message: str


@dataclass(frozen=True)
class TournamentView:
    tournament: Tournament
    matches: list[MatchView]
    links: list[tuple[int, int, str]]
    problems: list[TournamentProblemItem]


class TournamentViewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tournaments(self) -> list[Tournament]:
        return list((await self.session.execute(select(Tournament).order_by(
            Tournament.year.desc(), Tournament.start_date.desc(), Tournament.name,
        ))).scalars())

    async def get(self, tournament_id: int) -> Tournament:
        tournament = await self.session.get(Tournament, tournament_id)
        if tournament is None:
            raise TournamentNotFoundError("Турнир не найден.")
        return tournament

    async def update(self, tournament_id: int, **changes: object) -> Tournament:
        tournament = await self.get(tournament_id)
        allowed = {"structure_type", "tier", "environment", "start_date", "end_date"}
        for key, value in changes.items():
            if key in allowed:
                setattr(tournament, key, value)
        if tournament.start_date and tournament.end_date and tournament.start_date > tournament.end_date:
            raise ValueError("Дата начала турнира не может быть позже даты окончания.")
        await self.session.flush()
        return tournament

    async def view(self, tournament_id: int) -> TournamentView:
        tournament = await self.get(tournament_id)
        rows = list((await self.session.execute(select(Match).where(
            Match.tournament_id == tournament_id,
        ).order_by(Match.match_date, Match.round_number, Match.bracket_position, Match.id))).scalars())
        service = MatchService(self.session)
        views = [await service.get(match.id) for match in rows]
        links: list[tuple[int, int, str]] = []
        problems: list[TournamentProblemItem] = []
        by_id = {match.id: match for match in rows}
        for match in rows:
            if match.next_match_id is not None and match.next_match_id in by_id:
                links.append((match.id, match.next_match_id, "manual"))
            elif match.stage in STAGE_ORDER and match.stage != "final":
                candidates = self._next_candidates(match, rows)
                if len(candidates) == 1:
                    links.append((match.id, candidates[0].id, "inferred"))
                else:
                    problems.append(TournamentProblemItem(
                        match.id, "layout_unresolved",
                        "Не удалось однозначно определить следующий матч сетки.",
                    ))
            problems.extend(self._match_problems(match, next(v for v in views if v.match.id == match.id)))
        return TournamentView(tournament, views, links, problems)

    @staticmethod
    def _next_candidates(match: Match, matches: list[Match]) -> list[Match]:
        if match.winner_team_id is None:
            return []
        rank = STAGE_ORDER[match.stage]
        later_ranks = sorted({STAGE_ORDER[item.stage] for item in matches
                              if item.stage in STAGE_ORDER and STAGE_ORDER[item.stage] > rank})
        if not later_ranks:
            return []
        next_rank = later_ranks[0]
        return [item for item in matches if STAGE_ORDER.get(item.stage) == next_rank
                and item.match_date >= match.match_date
                and match.winner_team_id in {item.team_a_id, item.team_b_id}]

    @staticmethod
    def _match_problems(match: Match, view: MatchView) -> list[TournamentProblemItem]:
        result: list[TournamentProblemItem] = []
        add = lambda code, message: result.append(TournamentProblemItem(match.id, code, message))
        if match.resolution_status != "resolved": add("resolution", f"Статус серии: {match.resolution_status}.")
        if match.stage == "unknown": add("stage_unknown", "Этап серии не определён.")
        if match.team_a_id is None or match.team_b_id is None: add("unknown_team", "Одна или обе команды не определены.")
        if match.veto_data_status == "not_available": add("veto_missing", "Veto отсутствует.")
        elif match.veto_data_status in {"partial", "needs_review", "invalid"}: add("veto_review", f"Veto: {match.veto_data_status}.")
        failed = [item for item in view.maps if item.parse_status == "failed"]
        if failed: add("parse_failed", f"Ошибок парсинга карт: {len(failed)}.")
        expected = (match.team_a_maps_won + match.team_b_maps_won) if match.status == "completed" else {"bo1": 1, "bo3": 3, "bo5": 5}.get(match.format, len(view.maps))
        expected = max(expected, len(view.maps))
        if len(view.maps) < expected: add("demo_missing", f"Demo загружено {len(view.maps)}/{expected}.")
        names = [item.map_name for item in view.maps if item.map_name]
        if len(names) != len(set(names)): add("map_sequence", "В серии повторяется карта.")
        return result
