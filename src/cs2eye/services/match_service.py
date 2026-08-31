from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team, TeamRoster


class MatchNotFoundError(LookupError): pass
class MatchValidationError(ValueError): pass


@dataclass(frozen=True)
class MatchMap:
    demo_file_id: int
    map_number: int
    map_name: str | None
    team_a_score: int | None
    team_b_score: int | None
    winner_team_id: int | None
    map_role: str
    picked_by_team_id: int | None
    parse_status: str = "pending"
    source_deleted_at: str | None = None
    source_available: bool = False


@dataclass(frozen=True)
class MatchView:
    match: Match
    tournament: Tournament | None
    team_a: Team | None
    team_b: Team | None
    maps: list[MatchMap]


@dataclass(frozen=True)
class MatchStatLine:
    matches_played: int = 0
    matches_won: int = 0
    matches_lost: int = 0

    @property
    def match_win_rate(self) -> float | None:
        return self.matches_won / self.matches_played * 100 if self.matches_played else None


@dataclass(frozen=True)
class TeamMatchStats:
    team_id: int
    aggregation_level: str
    roster_id: int | None
    all: MatchStatLine
    by_format: dict[str, MatchStatLine]
    by_context: dict[str, MatchStatLine]


@dataclass(frozen=True)
class MatchBackfillResult:
    candidate_groups: int
    processed_groups: int
    resolved_matches: int
    needs_review_matches: int
    unresolved_matches: int
    failed_groups: int
    errors: list[str]


class MatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, team_id: int | None = None, resolution_status: str | None = None,
                   veto_filter: str | None = None) -> list[MatchView]:
        # Empty bracket slots belong to the tournament view, not to the global
        # user-facing match list. Showing them here creates fake Team A 0:0 Team B
        # cards before upstream matches have populated the participants.
        query = select(Match).where(
            Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
        ).order_by(Match.match_date.desc(), Match.id.desc())
        if team_id is not None: query = query.where(or_(Match.team_a_id == team_id, Match.team_b_id == team_id))
        if resolution_status is not None: query = query.where(Match.resolution_status == resolution_status)
        if veto_filter == "expected_missing":
            query = query.where(Match.resolution_status == "resolved", Match.format.in_(("bo1", "bo3", "bo5")), Match.team_a_id.is_not(None), Match.team_b_id.is_not(None), Match.veto_data_status == "not_available")
        elif veto_filter == "has_veto": query = query.where(Match.veto_data_status != "not_available")
        elif veto_filter is not None: raise MatchValidationError("veto_filter must be expected_missing or has_veto")
        return [await self.get(item.id) for item in (await self.session.execute(query)).scalars().all()]

    async def backfill(self) -> MatchBackfillResult:
        rows = (await self.session.execute(
            select(DemoFile.id, DemoFile.tournament_name, DemoFile.match_date,
                   DemoMapResult.team_a_id, DemoMapResult.team_b_id)
            .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .where(
                DemoMapResult.team_a_id.is_not(None), DemoMapResult.team_b_id.is_not(None),
                DemoMapResult.round_data_status == "complete",
                DemoMapResult.map_name.is_not(None), DemoMapResult.team_a_score.is_not(None),
                DemoMapResult.team_b_score.is_not(None),
                DemoMapResult.team_a_score != DemoMapResult.team_b_score,
                or_(DemoMapResult.team_a_score >= 13, DemoMapResult.team_b_score >= 13),
            ).order_by(DemoFile.match_date, DemoFile.id)
        )).all()
        groups: dict[tuple[str, date, int, int], int] = {}
        for demo_id, tournament, match_date, team_a_id, team_b_id in rows:
            low, high = sorted((team_a_id, team_b_id))
            groups.setdefault((tournament, match_date, low, high), demo_id)
        counts = {"resolved": 0, "needs_review": 0, "unresolved": 0}
        errors: list[str] = []
        processed = 0
        for key, demo_id in groups.items():
            try:
                view = await self.auto_group_demo(demo_id)
                counts[view.match.resolution_status] += 1
                processed += 1
            except Exception as error:
                errors.append(f"{key}: {error}")
        await self.session.flush()
        return MatchBackfillResult(len(groups), processed, counts["resolved"], counts["needs_review"],
                                   counts["unresolved"], len(errors), errors[:20])

    async def get(self, match_id: int) -> MatchView:
        match = await self.session.get(Match, match_id)
        if match is None: raise MatchNotFoundError("Матч не найден.")
        tournament = await self.session.get(Tournament, match.tournament_id) if match.tournament_id else None
        team_a = await self.session.get(Team, match.team_a_id) if match.team_a_id else None
        team_b = await self.session.get(Team, match.team_b_id) if match.team_b_id else None
        from cs2eye.models.demo import DemoParseRun
        rows = (await self.session.execute(
            select(DemoFile, DemoMapResult, DemoParseRun).join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .outerjoin(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id)
            .where(DemoFile.match_id == match_id).order_by(DemoFile.map_number, DemoFile.id)
        )).all()
        maps = [self._map(match, demo, result, run) for demo, result, run in rows]
        return MatchView(match, tournament, team_a, team_b, maps)

    async def create_scheduled(self, *, tournament_id: int, match_date: date,
            team_a_id: int | None, team_b_id: int | None, format: str, stage: str,
            environment: str, round_number: int | None = None, round_label: str | None = None,
            group_name: str | None = None, bracket_section: str | None = None,
            bracket_position: int | None = None) -> MatchView:
        if team_a_id is not None and team_a_id == team_b_id:
            raise MatchValidationError("Team A и Team B должны отличаться.")
        if await self.session.get(Tournament, tournament_id) is None:
            raise MatchValidationError("Турнир не найден.")
        for team_id in (team_a_id, team_b_id):
            if team_id is not None and await self.session.get(Team, team_id) is None:
                raise MatchValidationError("Команда не найдена.")
        match = Match(tournament_id=tournament_id, match_date=match_date,
            team_a_id=team_a_id, team_b_id=team_b_id, format=format, stage=stage,
            environment=environment, status="scheduled", resolution_status="resolved",
            team_a_maps_won=0, team_b_maps_won=0, winner_team_id=None,
            round_number=round_number, round_label=round_label, group_name=group_name,
            bracket_section=bracket_section, bracket_position=bracket_position,
            is_playoff=stage in {"round_of_32", "round_of_16", "quarterfinal", "semifinal", "final"})
        self.session.add(match)
        await self.session.flush()
        return await self.get(match.id)

    @staticmethod
    def _map(match: Match, demo: DemoFile, result: DemoMapResult, run=None) -> MatchMap:
        normal = result.team_a_id == match.team_a_id and result.team_b_id == match.team_b_id
        reverse = result.team_b_id == match.team_a_id and result.team_a_id == match.team_b_id
        score_a = result.team_a_score if normal else result.team_b_score if reverse else None
        score_b = result.team_b_score if normal else result.team_a_score if reverse else None
        winner = match.team_a_id if score_a is not None and score_b is not None and score_a > score_b else match.team_b_id if score_a is not None and score_b is not None and score_b > score_a else None
        from pathlib import Path
        from cs2eye.core.config import settings
        return MatchMap(demo.id, demo.map_number or 0, result.map_name, score_a, score_b, winner, demo.map_role, demo.picked_by_team_id,
                        run.status if run else "pending", demo.source_deleted_at.isoformat() if demo.source_deleted_at else None,
                        (Path(settings.demo_storage_root) / demo.storage_path).is_file())

    async def recalculate(self, match_id: int) -> MatchView:
        view = await self.get(match_id); match = view.match
        previous_result = (match.status, match.winner_team_id, match.team_a_maps_won, match.team_b_maps_won)
        if match.resolution_status != "resolved":
            match.team_a_maps_won = match.team_b_maps_won = 0; match.winner_team_id = None; match.status = "unknown"
            await self.session.flush()
            await self._propagate_winner(match, previous_result[1])
            await self._propagate_loser(match, previous_result[1])
            if previous_result != (match.status, match.winner_team_id, match.team_a_maps_won, match.team_b_maps_won):
                from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
                await invalidate_tournament_predictions(self.session, match.tournament_id)
            return await self.get(match_id)
        valid = [m for m in view.maps if m.team_a_score is not None and m.team_b_score is not None and m.team_a_score != m.team_b_score]
        if len(valid) != len(view.maps) or not valid:
            raise MatchValidationError("Resolved-серия должна содержать только валидные карты выбранной пары.")
        match.team_a_maps_won = sum(m.winner_team_id == match.team_a_id for m in valid)
        match.team_b_maps_won = sum(m.winner_team_id == match.team_b_id for m in valid)
        match.winner_team_id = match.team_a_id if match.team_a_maps_won > match.team_b_maps_won else match.team_b_id if match.team_b_maps_won > match.team_a_maps_won else None
        target = {"bo1": 1, "bo3": 2, "bo5": 3}.get(match.format)
        match.status = "completed" if target and max(match.team_a_maps_won, match.team_b_maps_won) >= target else "in_progress"
        await self.session.flush()
        await self._propagate_winner(match, previous_result[1])
        await self._propagate_loser(match, previous_result[1])
        if previous_result != (match.status, match.winner_team_id, match.team_a_maps_won, match.team_b_maps_won):
            from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
            await invalidate_tournament_predictions(self.session, match.tournament_id)
        return await self.get(match_id)

    async def _propagate_winner(self, match: Match, previous_winner_id: int | None) -> None:
        if match.next_match_id is None or match.next_match_slot not in {"team_a", "team_b"}:
            return
        target = await self.session.get(Match, match.next_match_id)
        if target is None or target.tournament_id != match.tournament_id:
            return
        field = "team_a_id" if match.next_match_slot == "team_a" else "team_b_id"
        current = getattr(target, field)
        if match.winner_team_id is None:
            if current == previous_winner_id:
                setattr(target, field, None)
        elif current is None or current == previous_winner_id or current == match.winner_team_id:
            setattr(target, field, match.winner_team_id)
        await self.session.flush()

    async def _propagate_loser(self, match: Match, previous_winner_id: int | None) -> None:
        if match.loser_next_match_id is None or match.loser_next_match_slot not in {"team_a", "team_b"}:
            return
        target = await self.session.get(Match, match.loser_next_match_id)
        if target is None or target.tournament_id != match.tournament_id:
            return
        participants = {match.team_a_id, match.team_b_id} - {None}
        loser_id = next(iter(participants - {match.winner_team_id}), None) if match.winner_team_id else None
        previous_loser_id = next(iter(participants - {previous_winner_id}), None) if previous_winner_id else None
        field = "team_a_id" if match.loser_next_match_slot == "team_a" else "team_b_id"
        current = getattr(target, field)
        if loser_id is None:
            if current == previous_loser_id:
                setattr(target, field, None)
        elif current is None or current == previous_loser_id or current == loser_id:
            setattr(target, field, loser_id)
        await self.session.flush()

    async def create_manual(
        self, demo_file_ids: list[int], *, format: str = "unknown", stage: str = "unknown",
        environment: str = "unknown", resolution_status: str = "resolved",
    ) -> MatchView:
        if not demo_file_ids or len(set(demo_file_ids)) != len(demo_file_ids):
            raise MatchValidationError("Нужен непустой список уникальных demo_file_id.")
        rows = (await self.session.execute(select(DemoFile, DemoMapResult).outerjoin(
            DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id).where(DemoFile.id.in_(demo_file_ids)))).all()
        if len(rows) != len(demo_file_ids): raise MatchValidationError("Одна или несколько демок не найдены.")
        ordered = sorted(rows, key=lambda row: demo_file_ids.index(row[0].id))
        ordered = self._canonical_split_maps(ordered)
        first_demo, first_result = ordered[0]
        if first_result is None or first_result.team_a_id is None or first_result.team_b_id is None:
            raise MatchValidationError("На первой карте не определены команды.")
        pair = {first_result.team_a_id, first_result.team_b_id}
        if any(result is None or {result.team_a_id, result.team_b_id} != pair for _, result in ordered):
            raise MatchValidationError("Все карты серии должны принадлежать одной паре команд.")
        if resolution_status == "resolved":
            if any(result.round_data_status != "complete" for _, result in ordered):
                raise MatchValidationError(
                    "Resolved-серия не может содержать неполный split-фрагмент demo."
                )
            if any(max(result.team_a_score or 0, result.team_b_score or 0) < 13 for _, result in ordered):
                raise MatchValidationError(
                    "Resolved-серия не может содержать незавершённую карту со счётом меньше 13."
                )
            map_names = [result.map_name for _, result in ordered]
            if None in map_names or len(map_names) != len(set(map_names)):
                raise MatchValidationError(
                    "Resolved-серия не может содержать одну карту дважды."
                )
        tournament = await self._tournament(first_demo)
        match = Match(tournament_id=tournament.id, match_date=first_demo.match_date,
            team_a_id=first_result.team_a_id, team_b_id=first_result.team_b_id, format=format,
            stage=stage, environment=environment, resolution_status=resolution_status,
            is_playoff=stage in {"round_of_32", "round_of_16", "quarterfinal", "semifinal", "final"})
        session_dates = {demo.match_date for demo, _ in ordered}; tournaments = {(demo.tournament_name, demo.match_date.year) for demo, _ in ordered}
        if len(session_dates) != 1 or len(tournaments) != 1:
            raise MatchValidationError("Карты разных дат или турниров нельзя объединить.")
        self.session.add(match); await self.session.flush()
        old_match_ids = {demo.match_id for demo, _ in ordered if demo.match_id is not None}
        for number, (demo, _) in enumerate(ordered, 1): demo.match_id, demo.map_number = match.id, number
        for old_id in old_match_ids:
            if old_id != match.id:
                deleted = await self._delete_if_empty(old_id)
                if not deleted: await self.recalculate(old_id)
        await self.session.flush(); return await self.recalculate(match.id)

    async def update(self, match_id: int, **changes: object) -> MatchView:
        match = await self.session.get(Match, match_id)
        if match is None: raise MatchNotFoundError("Матч не найден.")
        scoring_changed = any(
            key in changes and changes[key] is not None and changes[key] != getattr(match, key)
            for key in ("format", "resolution_status")
        )
        allowed = {"tournament_id", "format", "stage", "environment", "is_playoff", "is_elimination", "resolution_status",
                   "round_number", "round_label", "group_name", "bracket_section", "bracket_position", "next_match_id", "next_match_slot",
                   "loser_next_match_id", "loser_next_match_slot"}
        for transition_field in ("next_match_id", "loser_next_match_id"):
            if transition_field in changes and changes[transition_field] is not None:
                target = await self.session.get(Match, changes[transition_field])
                if target is None or target.id == match.id or target.tournament_id != match.tournament_id:
                    raise MatchValidationError("Следующий матч должен существовать в том же турнире.")
        if "tournament_id" in changes and changes["tournament_id"] is not None:
            if await self.session.get(Tournament, changes["tournament_id"]) is None:
                raise MatchValidationError("Турнир не найден.")
        if changes.get("next_match_id") is not None and changes.get("next_match_slot", match.next_match_slot) not in {"team_a", "team_b"}:
            raise MatchValidationError("Для следующего матча укажите слот team_a или team_b.")
        if changes.get("loser_next_match_id") is not None and changes.get("loser_next_match_slot", match.loser_next_match_slot) not in {"team_a", "team_b"}:
            raise MatchValidationError("Для перехода проигравшего укажите слот team_a или team_b.")
        nullable_layout = {"round_number", "round_label", "group_name", "bracket_section", "bracket_position", "next_match_id", "next_match_slot",
                           "loser_next_match_id", "loser_next_match_slot"}
        for key, value in changes.items():
            if key in allowed and (value is not None or key in nullable_layout): setattr(match, key, value)
        if match.stage in {"round_of_32", "round_of_16", "quarterfinal", "semifinal", "final"}: match.is_playoff = True
        await self.session.flush()
        from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
        await invalidate_tournament_predictions(self.session, match.tournament_id)
        if scoring_changed:
            return await self.recalculate(match_id)
        return await self.get(match_id)

    async def reorder(self, match_id: int, demo_file_ids: list[int]) -> MatchView:
        demos = list((await self.session.execute(select(DemoFile).where(DemoFile.match_id == match_id))).scalars().all())
        if {d.id for d in demos} != set(demo_file_ids) or len(demos) != len(demo_file_ids):
            raise MatchValidationError("Порядок должен содержать все карты серии ровно один раз.")
        by_id = {d.id: d for d in demos}
        for number, demo_id in enumerate(demo_file_ids, 1): by_id[demo_id].map_number = number
        await self.session.flush(); return await self.get(match_id)

    async def split(self, match_id: int, demo_file_ids: list[int] | None = None) -> list[MatchView]:
        match = await self.session.get(Match, match_id)
        if match is None: raise MatchNotFoundError("Матч не найден.")
        demos = list((await self.session.execute(select(DemoFile).where(DemoFile.match_id == match_id))).scalars().all())
        selected = [d for d in demos if demo_file_ids is None or d.id in demo_file_ids]
        if not selected: raise MatchValidationError("Не выбраны карты для разделения.")
        for demo in selected: demo.match_id = None; demo.map_number = None
        await self.session.flush()
        result = []
        for demo in selected: result.append(await self.auto_group_demo(demo.id, force_standalone=True))
        deleted = await self._delete_if_empty(match_id)
        if not deleted: await self.recalculate(match_id)
        return result

    async def auto_group_demo(self, demo_file_id: int, *, force_standalone: bool = False) -> MatchView:
        demo = await self.session.get(DemoFile, demo_file_id)
        if demo is None:
            raise MatchValidationError("Демка не найдена.")
        trigger_match_id = demo.match_id
        result = (await self.session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
        if result is None or result.team_a_id is None or result.team_b_id is None:
            raise MatchValidationError("Демка ещё не содержит определённую пару команд.")
        tournament = await self._tournament(demo); pair = sorted((result.team_a_id, result.team_b_id))
        if force_standalone:
            candidates = [(demo, result)]
        else:
            candidates = list((await self.session.execute(
                select(DemoFile, DemoMapResult).join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
                .where(DemoFile.tournament_name == demo.tournament_name, DemoFile.match_date == demo.match_date,
                    or_(and_(DemoMapResult.team_a_id == pair[0], DemoMapResult.team_b_id == pair[1]),
                        and_(DemoMapResult.team_a_id == pair[1], DemoMapResult.team_b_id == pair[0])),
                    DemoMapResult.round_data_status == "complete",
                    DemoMapResult.map_name.is_not(None),
                    DemoMapResult.team_a_score.is_not(None), DemoMapResult.team_b_score.is_not(None),
                    DemoMapResult.team_a_score != DemoMapResult.team_b_score,
                    or_(DemoMapResult.team_a_score >= 13, DemoMapResult.team_b_score >= 13))
                .order_by(DemoFile.id)
            )).all())
        numbered = [(self._filename_map_number(item.original_filename), item, map_result) for item, map_result in candidates]
        numbers = [n for n, _, _ in numbered if n is not None]
        confident = len(candidates) == 1 and bool(re.search(r"\bbo1\b", demo.original_filename, re.I))
        confident = confident or (len(numbers) == len(candidates) and sorted(numbers) == list(range(1, len(numbers) + 1)) and 2 <= len(numbers) <= 5)
        resolution = "resolved" if confident else "unresolved" if len(candidates) == 1 else "needs_review"
        fmt = (
            "bo1" if len(candidates) == 1 and confident
            else "bo3" if 2 <= len(candidates) <= 3
            else "bo5" if 4 <= len(candidates) <= 5
            else "unknown"
        )
        # Include matches left behind by split demo fragments. Once the final part is
        # stitched, earlier parts become partial and disappear from ``candidates``;
        # without this lookup they could leave a duplicate 0:0 series behind.
        group_match_ids = set() if force_standalone else set((await self.session.execute(
            select(DemoFile.match_id).join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .where(
                DemoFile.tournament_name == demo.tournament_name,
                DemoFile.match_date == demo.match_date,
                DemoFile.match_id.is_not(None),
                or_(
                    and_(DemoMapResult.team_a_id == pair[0], DemoMapResult.team_b_id == pair[1]),
                    and_(DemoMapResult.team_a_id == pair[1], DemoMapResult.team_b_id == pair[0]),
                ),
            )
        )).scalars().all())
        scheduled_ids: set[int] = set()
        if not force_standalone:
            scheduled_ids = set((await self.session.scalars(select(Match.id).where(
                Match.tournament_id == tournament.id,
                Match.match_date == demo.match_date,
                Match.status == "scheduled",
                or_(
                    and_(Match.team_a_id == pair[0], Match.team_b_id == pair[1]),
                    and_(Match.team_a_id == pair[1], Match.team_b_id == pair[0]),
                ),
            ))).all())
            if not scheduled_ids:
                adjacent_ids = list((await self.session.scalars(select(Match.id).where(
                    Match.tournament_id == tournament.id,
                    Match.match_date.between(
                        demo.match_date - timedelta(days=1),
                        demo.match_date + timedelta(days=1),
                    ),
                    Match.status == "scheduled",
                    or_(
                        and_(Match.team_a_id == pair[0], Match.team_b_id == pair[1]),
                        and_(Match.team_a_id == pair[1], Match.team_b_id == pair[0]),
                    ),
                ))).all())
                # A one-day discrepancy can come from tournament/source timezone
                # boundaries. Only accept it when the pair has exactly one slot;
                # ambiguity means these may be genuine repeat meetings.
                if len(adjacent_ids) == 1:
                    scheduled_ids = {adjacent_ids[0]}
            group_match_ids.update(scheduled_ids)
        # Prefer the pre-created schedule entry so its stage/bracket metadata and
        # stable public ID survive. Otherwise keep the match that triggered the
        # regrouping, preserving the previous behavior for demo-only series.
        existing_id = (
            min(scheduled_ids) if scheduled_ids
            else trigger_match_id if trigger_match_id in group_match_ids
            else min(group_match_ids, default=None)
        )
        existing = await self.session.get(Match, existing_id) if existing_id is not None else None
        match = existing or Match(tournament_id=tournament.id, match_date=demo.match_date,
            team_a_id=result.team_a_id, team_b_id=result.team_b_id, format=fmt,
            environment=tournament.environment, resolution_status=resolution)
        if existing is None: self.session.add(match); await self.session.flush()
        elif existing.resolution_status != "resolved": existing.format, existing.resolution_status = fmt, resolution
        candidate_ids = {item.id for _, item, _ in numbered}
        if group_match_ids:
            excluded_parts = list((await self.session.execute(select(DemoFile).where(
                DemoFile.match_id.in_(group_match_ids), DemoFile.id.not_in(candidate_ids),
            ))).scalars().all())
            for excluded in excluded_parts:
                excluded.match_id = None
                excluded.map_number = None
        ordered = sorted(numbered, key=lambda row: (row[0] is None, row[0] or row[1].id))
        for index, (_, item, _) in enumerate(ordered, 1): item.match_id, item.map_number = match.id, index
        await self.session.flush()
        for old_id in group_match_ids - {match.id}:
            deleted = await self._delete_if_empty(old_id)
            if not deleted: await self.recalculate(old_id)
        return await self.recalculate(match.id)

    async def _tournament(self, demo: DemoFile) -> Tournament:
        tournament = (await self.session.execute(select(Tournament).where(
            Tournament.name == demo.tournament_name, Tournament.year == demo.match_date.year))).scalar_one_or_none()
        if tournament is None:
            path = demo.storage_path.lower(); env = "lan" if "/lan/" in path else "online" if "/online/" in path else "unknown"
            tournament = Tournament(name=demo.tournament_name, year=demo.match_date.year, environment=env,
                                    start_date=demo.match_date, end_date=demo.match_date)
            self.session.add(tournament); await self.session.flush()
        else:
            tournament.start_date = min(tournament.start_date or demo.match_date, demo.match_date)
            tournament.end_date = max(tournament.end_date or demo.match_date, demo.match_date)
        return tournament

    async def _delete_if_empty(self, match_id: int) -> bool:
        remaining = (await self.session.execute(select(DemoFile.id).where(DemoFile.match_id == match_id).limit(1))).scalar_one_or_none()
        if remaining is None:
            match = await self.session.get(Match, match_id)
            if match: await self.session.delete(match)
            return True
        return False

    @staticmethod
    def _filename_map_number(filename: str) -> int | None:
        match = re.search(r"(?:^|[-_. ])(?:map|m)([1-5])(?:[-_. ]|$)", filename, re.I)
        return int(match.group(1)) if match else None

    @staticmethod
    def _split_part(filename: str) -> tuple[str, int] | None:
        match = re.match(r"^(.*)-p([1-9])\.dem$", filename, re.IGNORECASE)
        return (match.group(1).casefold(), int(match.group(2))) if match else None

    @classmethod
    def _canonical_split_maps(
        cls, rows: list[tuple[DemoFile, DemoMapResult]],
    ) -> list[tuple[DemoFile, DemoMapResult]]:
        """Keep only the final, stitched file from each split-demo sequence."""
        final_by_key: dict[str, tuple[int, DemoFile, DemoMapResult]] = {}
        for demo, result in rows:
            part = cls._split_part(demo.original_filename)
            if part is not None:
                current = final_by_key.get(part[0])
                if current is None or part[1] > current[0]:
                    final_by_key[part[0]] = (part[1], demo, result)
        superseded = {
            demo.id
            for demo, _ in rows
            if (part := cls._split_part(demo.original_filename)) is not None
            and final_by_key[part[0]][1].id != demo.id
        }
        return [(demo, result) for demo, result in rows if demo.id not in superseded]

    async def team_stats(self, team_id: int, *, aggregation_level: Literal["organization", "current_roster"] = "organization") -> TeamMatchStats:
        team = await self.session.get(Team, team_id)
        if team is None: raise MatchValidationError("Команда не найдена.")
        matches = list((await self.session.execute(select(Match).where(Match.resolution_status == "resolved",
            Match.status == "completed", or_(Match.team_a_id == team_id, Match.team_b_id == team_id)))).scalars().all())
        if aggregation_level == "current_roster":
            if team.current_roster_id is None: matches = []
            else: matches = [m for m in matches if await self._match_uses_roster(m.id, team_id, team.current_roster_id)]
        def line(items: list[Match]) -> MatchStatLine:
            wins = sum(m.winner_team_id == team_id for m in items)
            return MatchStatLine(len(items), wins, len(items) - wins)
        formats = {key: line([m for m in matches if m.format == key]) for key in ("bo1", "bo3", "bo5")}
        contexts = {
            "lan": line([m for m in matches if m.environment == "lan"]),
            "online": line([m for m in matches if m.environment == "online"]),
            "playoff": line([m for m in matches if m.is_playoff]),
            "elimination": line([m for m in matches if m.is_elimination]),
            "final": line([m for m in matches if m.stage == "final"]),
        }
        return TeamMatchStats(team_id, aggregation_level, team.current_roster_id if aggregation_level == "current_roster" else None, line(matches), formats, contexts)

    async def _match_uses_roster(self, match_id: int, team_id: int, roster_id: int) -> bool:
        demo_ids = list((await self.session.execute(select(DemoFile.id).where(DemoFile.match_id == match_id))).scalars().all())
        linked = set((await self.session.execute(select(DemoTeamRoster.demo_file_id).where(
            DemoTeamRoster.demo_file_id.in_(demo_ids), DemoTeamRoster.team_id == team_id,
            DemoTeamRoster.roster_id == roster_id, DemoTeamRoster.resolution_status == "complete"))).scalars().all())
        return bool(demo_ids) and linked == set(demo_ids)
