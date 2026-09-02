from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import (
    Player,
    Team,
    TeamParticipantMembership,
    TeamRankingSnapshot,
    TeamRoster,
    TeamRosterMember,
)
from cs2eye.services.analyst_context_service import AnalystContextService
from cs2eye.services.calculated_veto_service import CalculatedVetoService
from cs2eye.services.form_context_service import FormContextService
from cs2eye.services.opponent_context_service import OpponentContextService
from cs2eye.services.he_kill_by_map_service import HEKillByMapService
from cs2eye.services.betting_restriction_service import betting_restrictions_for_teams
from cs2eye.services.leadership_service import LeadershipService
from cs2eye.services.matchup_service import MatchupService
from cs2eye.services.team_comparison_service import TeamComparisonService
from cs2eye.services.team_h2h_service import TeamH2HService
from cs2eye.services.team_map_strength_service import calculate_map_strength
from cs2eye.services.win_probability_service import predict_win_probability


MAX_CURRENT_TOURNAMENT_EVIDENCE = 5
MAX_OTHER_EVIDENCE = 5
MAX_TOTAL_EVIDENCE = 10
MAX_KEY_EDGES = 5
MAX_STRENGTH_FACTORS = 5
EDGE_SMALL_THRESHOLD = 5.0
EDGE_MODERATE_THRESHOLD = 10.0
EDGE_CLEAR_THRESHOLD = 20.0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _rate(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number * 100 if -1 <= number <= 1 else number


def _nested(payload: dict | None, *path: str) -> float | None:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _rate(value)


def edge_strength(difference: float) -> str | None:
    difference = abs(difference)
    if difference >= EDGE_CLEAR_THRESHOLD:
        return "clear"
    if difference >= EDGE_MODERATE_THRESHOLD:
        return "moderate"
    if difference >= EDGE_SMALL_THRESHOLD:
        return "small"
    return None


class MatchAnalysisContextBuilder:
    """Orchestrate existing analytics into MatchAnalysisContext v1."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build(
        self,
        team_a_id: int,
        team_b_id: int,
        *,
        as_of: datetime,
        match_id: int | None = None,
        tournament_id: int | None = None,
        match_format: str | None = None,
        analysis_mode: str = "pre_match",
    ) -> MatchAnalysisContext:
        if team_a_id == team_b_id:
            raise ValueError("Нужны две разные команды.")
        if analysis_mode not in {"pre_match", "post_match"}:
            raise ValueError("analysis_mode must be pre_match or post_match")
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)
        cutoff = as_of.date()
        historical = cutoff < date.today()

        teams = list((await self.session.scalars(
            select(Team).where(Team.id.in_((team_a_id, team_b_id)))
        )).all())
        by_id = {team.id: team for team in teams}
        if team_a_id not in by_id or team_b_id not in by_id:
            raise LookupError("Команда не найдена.")

        match, tournament = await self._match_metadata(
            team_a_id, team_b_id, match_id, tournament_id,
        )
        effective_tournament_id = match.tournament_id if match else tournament_id
        stored_match_format = match.format if match and match.format in {"bo1", "bo3", "bo5"} else None
        if match_format is not None and match_format not in {"bo1", "bo3", "bo5"}:
            raise ValueError("match_format must be bo1, bo3 or bo5")
        if stored_match_format and match_format and stored_match_format != match_format:
            raise ValueError("match_format не совпадает с форматом матча.")
        match_format = stored_match_format or match_format
        match_environment = match.environment if match and match.environment in {"lan", "online"} else None
        service_mode = "post_veto" if analysis_mode == "post_match" else "pre_veto"

        limitations: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []

        matchup_payload: dict | None = None
        prediction_payload = await self._prediction(
            team_a_id, team_b_id, match_format, service_mode, cutoff, match_id,
        )
        if prediction_payload.get("matchup"):
            matchup_payload = prediction_payload["matchup"]
        if matchup_payload is None and match_format:
            try:
                matchup_payload = await MatchupService(self.session).calculate(
                    team_a_id, team_b_id, match_format, service_mode, cutoff, match_id,
                )
            except ValueError as error:
                limitations.append(f"Matchup unavailable: {error}")
        if matchup_payload:
            limitations.extend(str(item) for item in matchup_payload.get("limitations", []))

        form_pair = (matchup_payload or {}).get("form_context")
        if not form_pair:
            form_pair = await FormContextService(self.session).compare(
                team_a_id, team_b_id, cutoff, effective_tournament_id, match_id,
            )

        comparison = None
        leadership: dict[int, dict | None] = {team_a_id: None, team_b_id: None}
        if not historical:
            comparison = await TeamComparisonService(self.session, now=as_of).compare(
                team_a_id, team_b_id,
            )
            for team_id in (team_a_id, team_b_id):
                try:
                    leadership[team_id] = await LeadershipService(self.session).team(team_id)
                except ValueError as error:
                    warnings.append(f"Leadership unavailable for team {team_id}: {error}")
        else:
            limitations.append(
                "Current Team Strength, Leadership and map aggregates were excluded for a historical as_of."
            )

        ranks = await self._ranks_as_of((team_a_id, team_b_id), cutoff, by_id)
        roster_contexts = await self._rosters_as_of((team_a_id, team_b_id), cutoff, by_id)
        comparison_sides = {}
        if comparison:
            comparison_sides = {
                team_a_id: comparison.team_a,
                team_b_id: comparison.team_b,
            }

        team_contexts = {}
        for side, team_id, form_key in (
            ("team_a", team_a_id, "team_a_form_context"),
            ("team_b", team_b_id, "team_b_form_context"),
        ):
            team_contexts[side] = self._team_context(
                by_id[team_id], ranks.get(team_id), roster_contexts[team_id],
                comparison_sides.get(team_id), form_pair.get(form_key, {}),
                leadership[team_id],
            )

        form_service = FormContextService(self.session)
        evidence_a = await form_service.recent_series_evidence(
            team_a_id, as_of=cutoff, tournament_id=effective_tournament_id,
            exclude_match_id=match_id,
            current_limit=MAX_CURRENT_TOURNAMENT_EVIDENCE,
            other_limit=MAX_OTHER_EVIDENCE, total_limit=MAX_TOTAL_EVIDENCE,
        )
        evidence_b = await form_service.recent_series_evidence(
            team_b_id, as_of=cutoff, tournament_id=effective_tournament_id,
            exclude_match_id=match_id,
            current_limit=MAX_CURRENT_TOURNAMENT_EVIDENCE,
            other_limit=MAX_OTHER_EVIDENCE, total_limit=MAX_TOTAL_EVIDENCE,
        )
        opponent_service=OpponentContextService(self.session)
        opponent_a=await opponent_service.calculate(team_a_id,cutoff,effective_tournament_id)
        opponent_b=await opponent_service.calculate(team_b_id,cutoff,effective_tournament_id)
        opponent_fields=("version","adjusted_form_version","raw_form_score","opponent_adjusted_form_score","tournament_opponent_adjusted_form_score","dynamic_sos_score","reliability")
        result_fields=("opponent","result","series_score","opponent_dynamic_strength","opponent_reliability","result_quality_score","result_quality_label")
        def opponent_payload(value):return {**{key:value[key] for key in opponent_fields},"matches":[{key:item[key] for key in result_fields} for item in value["matches"]]}
        opponent_context={"team_a":opponent_payload(opponent_a),"team_b":opponent_payload(opponent_b)}

        veto_payload = None
        if match_format == "bo3" and not historical:
            try:
                veto_payload = await CalculatedVetoService(self.session, today=cutoff).calculate(
                    team_a_id, team_b_id, match_format, as_of=cutoff,
                    exclude_match_id=match_id,
                )
            except ValueError as error:
                warnings.append(f"Calculated veto unavailable: {error}")
        likely_maps = self._likely_maps(veto_payload)
        map_matchups = await self._map_matchups(
            (team_a_id, team_b_id), likely_maps, veto_payload, historical,
        )

        h2h_payload = await TeamH2HService(self.session, today=cutoff).compare(
            team_a_id, team_b_id, recent_limit=10, as_of=cutoff,
        )
        h2h_context = self._h2h_context(h2h_payload, historical)
        if historical:
            warnings.append("Current-roster H2H is unavailable for historical reconstruction.")

        he_kill_by_map = await HEKillByMapService(self.session).calculate(
            team_a_id, team_b_id, as_of=as_of, exclude_match_id=match_id,
        )

        relevant_maps = [item["map"] for item in likely_maps]
        manual = {
            "source_type": "manual_analyst_note",
            "team_a": await self._manual_notes(
                team_a_id, as_of, relevant_maps, match_environment,
                {item["id"] for item in roster_contexts[team_a_id]["players"] if item["id"]},
            ),
            "team_b": await self._manual_notes(
                team_b_id, as_of, relevant_maps, match_environment,
                {item["id"] for item in roster_contexts[team_b_id]["players"] if item["id"]},
            ),
        }

        prediction = self._prediction_context(prediction_payload)
        matchup = self._matchup_context(matchup_payload)
        veto = {
            "source_type": "deterministic_analytics",
            "basis": "calculated_veto",
            "model_version": veto_payload.get("calculated_veto_model_version") if veto_payload else None,
            "likely_maps": likely_maps,
        }

        self._collect_quality(
            team_contexts, prediction, matchup, veto, map_matchups, h2h_context,
            evidence_a, evidence_b, missing, warnings, limitations,
        )
        data_quality = self._data_quality(missing, warnings, limitations)

        return MatchAnalysisContext.model_validate({
            "schema_version": "match_analysis_context.v1",
            "generated_at": datetime.now(UTC),
            "as_of": as_of,
            "analysis_mode": analysis_mode,
            "match": self._match_context(match, tournament, match_format),
            "teams": team_contexts,
            "recent_series_evidence": {"team_a": evidence_a, "team_b": evidence_b},
            "opponent_context": opponent_context,
            "prediction": prediction,
            "matchup": matchup,
            "veto": veto,
            "map_matchups": map_matchups,
            "h2h": h2h_context,
            "manual_context": manual,
            "secondary_bets": {"he_kill_by_map": he_kill_by_map},
            "betting_restrictions": betting_restrictions_for_teams(
                teams, is_playoff=match.is_playoff if match else None,
            ),
            "data_quality": data_quality,
        })

    async def _match_metadata(
        self, team_a_id: int, team_b_id: int, match_id: int | None,
        tournament_id: int | None,
    ) -> tuple[Match | None, Tournament | None]:
        match = await self.session.get(Match, match_id) if match_id else None
        if match_id and match is None:
            raise LookupError("Матч не найден.")
        if match and {match.team_a_id, match.team_b_id} != {team_a_id, team_b_id}:
            raise ValueError("Матч не принадлежит выбранной паре команд.")
        if match and tournament_id is not None and match.tournament_id != tournament_id:
            raise ValueError("tournament_id не совпадает с турниром матча.")
        resolved_tournament_id = match.tournament_id if match else tournament_id
        tournament = await self.session.get(Tournament, resolved_tournament_id) if resolved_tournament_id else None
        if tournament_id and tournament is None:
            raise LookupError("Турнир не найден.")
        return match, tournament

    @staticmethod
    def _match_context(
        match: Match | None, tournament: Tournament | None,
        effective_format: str | None = None,
    ) -> dict:
        return {
            "id": match.id if match else None,
            "date": match.match_date if match else None,
            "format": effective_format,
            "environment": match.environment if match and match.environment in {"lan", "online"} else None,
            "stage": match.stage if match and match.stage != "unknown" else None,
            "is_playoff": match.is_playoff if match else None,
            "is_elimination": match.is_elimination if match else None,
            "tournament": {
                "id": tournament.id if tournament else None,
                "name": tournament.name if tournament else None,
                "tier": tournament.tier if tournament else None,
            },
            "round_number": match.round_number if match else None,
            "round_label": match.round_label if match else None,
            "section": match.bracket_section if match else None,
        }

    async def _prediction(
        self, a: int, b: int, match_format: str | None, mode: str,
        cutoff: date, match_id: int | None,
    ) -> dict:
        if match_format is None:
            return {
                "prediction_status": "not_available", "model_version": None,
                "quality_gate_passed": None,
                "team_a": {"probability": None}, "team_b": {"probability": None},
                "confidence": None, "explanation": None,
            }
        try:
            return await predict_win_probability(
                self.session, a=a, b=b, format=match_format, mode=mode,
                as_of=cutoff, series_id=match_id,
            )
        except ValueError:
            return {
                "prediction_status": "not_available", "model_version": None,
                "quality_gate_passed": None,
                "team_a": {"probability": None}, "team_b": {"probability": None},
                "confidence": None, "explanation": None,
            }

    @staticmethod
    def _prediction_context(payload: dict) -> dict:
        status = payload.get("prediction_status", "not_available")
        if status not in {"available", "not_available", "model_not_trained", "insufficient_data"}:
            status = "not_available"
        drivers = []
        for index, item in enumerate((payload.get("explanation") or {}).get("top_factors", [])[:5]):
            favored = item.get("favors")
            drivers.append({
                "driver_id": f"ml:{item.get('key', index)}",
                "key": str(item.get("key", index)),
                "favored_team": favored if favored in {"team_a", "team_b"} else None,
                "importance": abs(float(item.get("impact_percentage_points", 0))),
                "reliability": _number(payload.get("confidence")),
            })
        return {
            "source_type": "ml_prediction",
            "status": status,
            "model_version": payload.get("model_version"),
            "quality_gate_passed": payload.get("quality_gate_passed"),
            "team_a_probability": (payload.get("team_a") or {}).get("probability"),
            "team_b_probability": (payload.get("team_b") or {}).get("probability"),
            "confidence": payload.get("confidence"),
            "top_model_drivers": drivers,
        }

    @staticmethod
    def _matchup_context(payload: dict | None) -> dict:
        if not payload:
            return {
                "source_type": "deterministic_analytics", "model_version": None,
                "team_a_score": None, "team_b_score": None,
                "reliability": None, "confidence_level": None, "factors": [],
            }
        factors = []
        for item in payload.get("factors", []):
            score_a = _number(item.get("score", item.get("normalized_score")))
            factors.append({
                "factor_id": f"matchup:{item.get('key', 'unknown')}",
                "key": str(item.get("key", "unknown")),
                "team_a_score": score_a,
                "team_b_score": round(100 - score_a, 2) if score_a is not None else None,
                "reliability": item.get("confidence"),
                "sample_size": item.get("sample_size", item.get("sample")),
            })
        return {
            "source_type": "deterministic_analytics",
            "model_version": payload.get("model_version"),
            "team_a_score": (payload.get("team_a") or {}).get("score"),
            "team_b_score": (payload.get("team_b") or {}).get("score"),
            "reliability": payload.get("reliability"),
            "confidence_level": payload.get("confidence_level"),
            "factors": factors,
        }

    async def _ranks_as_of(
        self, team_ids: tuple[int, int], cutoff: date, teams: dict[int, Team],
    ) -> dict[int, int | None]:
        rows = list((await self.session.scalars(select(TeamRankingSnapshot).where(
            TeamRankingSnapshot.team_id.in_(team_ids),
            TeamRankingSnapshot.ranking_date <= cutoff,
        ).order_by(TeamRankingSnapshot.team_id, TeamRankingSnapshot.ranking_date))).all())
        result: dict[int, int | None] = {team_id: None for team_id in team_ids}
        for row in rows:
            result[row.team_id] = row.rank
        for team_id in team_ids:
            team = teams[team_id]
            if result[team_id] is None and team.ranking_date and team.ranking_date <= cutoff:
                result[team_id] = team.current_rank
        return result

    async def _rosters_as_of(
        self, team_ids: tuple[int, int], cutoff: date, teams: dict[int, Team],
    ) -> dict[int, dict]:
        rows = list((await self.session.scalars(select(TeamRoster).where(
            TeamRoster.team_id.in_(team_ids),
            or_(TeamRoster.active_from.is_(None), TeamRoster.active_from <= cutoff),
            or_(TeamRoster.active_to.is_(None), TeamRoster.active_to > cutoff),
        ).order_by(TeamRoster.team_id, TeamRoster.active_from, TeamRoster.id))).all())
        selected: dict[int, TeamRoster] = {}
        for row in rows:
            if row.resolution_status == "complete":
                selected[row.team_id] = row
        if cutoff >= date.today():
            for team_id in team_ids:
                current_id = teams[team_id].current_roster_id
                current = next((row for row in rows if row.id == current_id), None)
                if current and current.resolution_status == "complete":
                    selected[team_id] = current

        roster_ids = [row.id for row in selected.values()]
        member_rows = (await self.session.execute(
            select(TeamRosterMember, Player).outerjoin(
                Player, Player.id == TeamRosterMember.player_id,
            ).where(TeamRosterMember.roster_id.in_(roster_ids))
            .order_by(TeamRosterMember.roster_id, TeamRosterMember.id)
        )).all() if roster_ids else []
        members: dict[int, list[dict]] = defaultdict(list)
        for member, player in member_rows:
            members[member.roster_id].append({
                "id": member.player_id,
                "name": player.nickname if player else member.player_name_snapshot,
                "role": member.role_snapshot,
            })

        cutoff_end = datetime.combine(cutoff, time.max, tzinfo=UTC)
        coach_rows = (await self.session.execute(select(
            TeamParticipantMembership, Player,
        ).join(Player, Player.id == TeamParticipantMembership.player_id).where(
            TeamParticipantMembership.team_id.in_(team_ids),
            TeamParticipantMembership.participant_type == "coach",
            or_(TeamParticipantMembership.joined_at.is_(None), TeamParticipantMembership.joined_at <= cutoff_end),
            or_(TeamParticipantMembership.left_at.is_(None), TeamParticipantMembership.left_at > cutoff_end),
        ))).all()
        coaches = {
            membership.team_id: {"id": player.id, "name": player.nickname}
            for membership, player in coach_rows
            if cutoff >= date.today() or membership.joined_at is not None
        }
        return {
            team_id: {
                "roster_id": selected.get(team_id).id if team_id in selected else None,
                "players": members.get(selected[team_id].id, []) if team_id in selected else [],
                "coach": coaches.get(team_id),
            }
            for team_id in team_ids
        }

    @staticmethod
    def _team_context(
        team: Team, rank: int | None, roster: dict, comparison_side: Any,
        form: dict, leadership: dict | None,
    ) -> dict:
        strength = comparison_side.strength if comparison_side else None
        factors = []
        stability_score = None
        stability_reliability = None
        sample_maps = 0
        if strength:
            ordered = sorted(
                [factor for factor in strength.factors if factor.available],
                key=lambda factor: abs(factor.impact), reverse=True,
            )[:MAX_STRENGTH_FACTORS]
            factors = [{
                "factor_id": f"team_strength:{factor.key}",
                "key": factor.key,
                "score": factor.normalized_score,
                "reliability": factor.confidence,
            } for factor in ordered]
            stability = next((factor for factor in strength.factors if factor.key == "roster_stability"), None)
            if stability:
                stability_score = stability.normalized_score
                stability_reliability = stability.confidence
                sample_maps = stability.sample_size or 0
        igl = (leadership or {}).get("igl")
        coach = (leadership or {}).get("coach")
        leadership_samples = [
            int(item.get("sample", {}).get("maps", 0)) for item in (igl, coach) if item
        ]
        leadership_reliabilities = [
            float(item["reliability"]) for item in (igl, coach)
            if item and item.get("reliability") is not None
        ]
        return {
            "id": team.id,
            "name": team.name,
            "rank": rank,
            "roster": {
                **roster,
                "stability_score": stability_score,
                "reliability": stability_reliability,
                "sample_maps": sample_maps,
            },
            "team_strength": {
                "score": strength.final_score if strength else None,
                "reliability": strength.reliability if strength else None,
                "sample_size": max((factor.sample_size or 0 for factor in strength.factors), default=0) if strength else 0,
                "key_factors": factors,
            },
            "form": {
                "tournament_form_score": form.get("tournament_form_score"),
                "tournament_matches": form.get("tournament_matches_count", 0),
                "tournament_reliability": form.get("tournament_reliability"),
                "recent_60d_score": form.get("recent_60d_adjusted_form_score"),
                "recent_60d_matches": form.get("recent_60d_matches_count", 0),
                "recent_60d_reliability": form.get("recent_60d_reliability"),
                "strength_of_schedule_score": form.get("strength_of_schedule_score"),
                "performance_vs_expectation_score": form.get("performance_vs_expectation_score"),
                "matches_vs_top_5": form.get("top5_matches_60d", 0),
                "matches_vs_top_10": form.get("top10_matches_60d", 0),
                "matches_vs_top_30": form.get("top30_matches_60d", 0),
            },
            "leadership": {
                "igl_score": igl.get("score") if igl else None,
                "coach_score": coach.get("score") if coach else None,
                "reliability": min(leadership_reliabilities) if leadership_reliabilities else None,
                "sample_size": max(leadership_samples, default=0),
            },
        }

    @staticmethod
    def _likely_maps(veto: dict | None) -> list[dict]:
        if not veto:
            return []
        result = []
        for item in veto.get("maps", [])[:3]:
            roles = {
                "team_a_pick": float(item.get("pick_by_team_a_probability", 0)),
                "team_b_pick": float(item.get("pick_by_team_b_probability", 0)),
                "decider": float(item.get("decider_probability", 0)),
            }
            role, probability = max(roles.items(), key=lambda pair: pair[1])
            result.append({
                "map": item["map"],
                "series_probability": item.get("series_map_probability"),
                "confidence": item.get("confidence"),
                "likely_role": role if probability > 0 else "unknown",
            })
        return result

    async def _map_matchups(
        self, team_ids: tuple[int, int], likely_maps: list[dict],
        veto: dict | None, historical: bool,
    ) -> list[dict]:
        if historical or not likely_maps:
            return []
        map_names = [item["map"] for item in likely_maps]
        rows = list((await self.session.scalars(select(TeamMapAggregate).where(
            TeamMapAggregate.team_id.in_(team_ids),
            TeamMapAggregate.map_name.in_(map_names),
        ))).all())
        scopes: dict[tuple[int, str], dict[str, TeamMapAggregate]] = defaultdict(dict)
        for row in rows:
            level_ok = row.aggregation_level == "organization" and row.roster_id is None
            if level_ok:
                scopes[(row.team_id, row.map_name)][row.scope_key] = row
        veto_maps = {item["map"]: item for item in (veto or {}).get("maps", [])}
        relevance = {item["map"]: item for item in likely_maps}
        result = []
        for map_name in map_names:
            a_scopes = scopes.get((team_ids[0], map_name), {})
            b_scopes = scopes.get((team_ids[1], map_name), {})
            a_strength = calculate_map_strength(a_scopes) if a_scopes else None
            b_strength = calculate_map_strength(b_scopes) if b_scopes else None
            a_all, b_all = a_scopes.get("all"), b_scopes.get("all")
            edges = self._key_edges(map_name, a_all, b_all, a_strength, b_strength)
            calculated = veto_maps.get(map_name, {})
            result.append({
                "map": map_name,
                "relevance": relevance[map_name].get("series_probability"),
                "team_a": {
                    "map_strength": a_strength.map_strength_score if a_strength else None,
                    "reliability": a_strength.reliability if a_strength else None,
                    "sample_maps": a_all.maps_played if a_all else 0,
                },
                "team_b": {
                    "map_strength": b_strength.map_strength_score if b_strength else None,
                    "reliability": b_strength.reliability if b_strength else None,
                    "sample_maps": b_all.maps_played if b_all else 0,
                },
                "matchup_score_team_a": (calculated.get("team_a") or {}).get("matchup_map_score"),
                "key_edges": edges,
            })
        return result

    @staticmethod
    def _key_edges(
        map_name: str, a: TeamMapAggregate | None, b: TeamMapAggregate | None,
        a_strength: Any, b_strength: Any,
    ) -> list[dict]:
        if not a or not b:
            return []
        candidates = {
            "ct_side": (_rate(a.ct_win_rate), _rate(b.ct_win_rate)),
            "t_side": (_rate(a.t_win_rate), _rate(b.t_win_rate)),
            "opening": (_nested(a.combat_data, "opening", "conversion_rate"), _nested(b.combat_data, "opening", "conversion_rate")),
            "trade": (_nested(a.combat_data, "trade", "trade_rate"), _nested(b.combat_data, "trade", "trade_rate")),
            "clutch": (_nested(a.combat_data, "clutch", "win_rate"), _nested(b.combat_data, "clutch", "win_rate")),
            "postplant": (_rate(a.postplant_win_rate), _rate(b.postplant_win_rate)),
            "retake": (_rate(a.retake_win_rate), _rate(b.retake_win_rate)),
            "pistol": (_nested(a.economy_data, "pistol", "win_rate"), _nested(b.economy_data, "pistol", "win_rate")),
            "force_buy": (_nested(a.economy_data, "force_vs_full_buy", "win_rate"), _nested(b.economy_data, "force_vs_full_buy", "win_rate")),
            "full_buy": (_nested(a.economy_data, "full_buy_vs_full_buy", "win_rate"), _nested(b.economy_data, "full_buy_vs_full_buy", "win_rate")),
            "anti_eco": (_nested(a.economy_data, "anti_eco", "win_rate"), _nested(b.economy_data, "anti_eco", "win_rate")),
            "utility": (_nested(a.utility_data, "impact", "score"), _nested(b.utility_data, "impact", "score")),
        }
        reliability_values = [
            _number(getattr(item, "reliability", None)) for item in (a_strength, b_strength)
        ]
        reliability = min((value for value in reliability_values if value is not None), default=None)
        ranked = []
        for metric, (value_a, value_b) in candidates.items():
            if value_a is None or value_b is None:
                continue
            difference = value_a - value_b
            strength = edge_strength(difference)
            if strength:
                ranked.append((abs(difference), {
                    "evidence_id": f"map:{map_name}:{metric}",
                    "metric": metric,
                    "favored_team": "team_a" if difference > 0 else "team_b",
                    "strength": strength,
                    "reliability": reliability,
                }))
        return [payload for _, payload in sorted(ranked, key=lambda item: -item[0])[:MAX_KEY_EDGES]]

    @staticmethod
    def _h2h_context(payload: Any, historical: bool) -> dict:
        def scope(item: Any, *, unavailable: bool = False) -> dict:
            status_map = {
                "available": "available",
                "partial_data": "partial_data",
                "no_meetings": "no_meetings",
                "current_rosters_never_met": "no_meetings",
                "current_roster_unavailable": "roster_unavailable",
            }
            status = "roster_unavailable" if unavailable else status_map.get(item.status, "partial_data")
            return {
                "status": status,
                "series_played": 0 if unavailable else item.series_played,
                "maps_played": 0 if unavailable else item.maps_played,
                "team_a_series_won": 0 if unavailable else item.team_a_series_won,
                "team_b_series_won": 0 if unavailable else item.team_b_series_won,
                "team_a_maps_won": 0 if unavailable else item.team_a.maps_won,
                "team_b_maps_won": 0 if unavailable else item.team_b.maps_won,
                "team_a_rating": None if unavailable else item.team_a.h2h_rating,
                "team_b_rating": None if unavailable else item.team_b.h2h_rating,
                "team_a_score": None if unavailable else item.team_a.performance_score,
                "team_b_score": None if unavailable else item.team_b.performance_score,
                "confidence": None if unavailable else item.confidence_score / 100,
            }
        applicability_map = {
            "direct": "high", "high": "high", "medium": "medium",
            "low": "low", "unknown": "none",
        }
        current_unavailable = historical
        current = scope(payload.current_rosters, unavailable=current_unavailable)
        applicability = "none" if current_unavailable else applicability_map.get(
            payload.roster_context.history_applicability, "none",
        )
        preferred = "current_rosters" if current["maps_played"] else "organizations"
        return {
            "preferred_scope": preferred,
            "history_applicability": applicability,
            "organizations": scope(payload.organizations),
            "current_rosters": current,
        }

    async def _manual_notes(
        self, team_id: int, as_of: datetime, maps: list[str],
        environment: str | None, roster_player_ids: set[int],
    ) -> list[dict]:
        relevant, _ = await AnalystContextService(self.session).relevant(
            team_id, maps=maps, environment=environment, as_of=as_of,
        )
        map_set = set(maps)
        result = []
        for factor in relevant:
            if factor.map_name and factor.map_name not in map_set:
                continue
            if environment and factor.environment not in {"any", environment}:
                continue
            if factor.players and roster_player_ids and not any(
                player.id in roster_player_ids for player in factor.players
            ):
                continue
            result.append({
                "note_id": f"analyst_factor:{factor.id}",
                "polarity": factor.factor_type,
                "category": factor.category,
                "players": [player.nickname for player in factor.players],
                "coach": factor.coach.nickname if factor.coach else None,
                "map": factor.map_name,
                "environment": None if factor.environment == "any" else factor.environment,
                "text": factor.text,
            })
        return result

    @staticmethod
    def _collect_quality(
        teams: dict, prediction: dict, matchup: dict, veto: dict,
        maps: list[dict], h2h: dict, evidence_a: list, evidence_b: list,
        missing: list[str], warnings: list[str], limitations: list[str],
    ) -> None:
        if prediction["status"] != "available":
            missing.append("prediction")
        if matchup["team_a_score"] is None or matchup["team_b_score"] is None:
            missing.append("matchup")
        if not veto["likely_maps"]:
            missing.append("veto")
        if not maps:
            missing.append("map_matchups")
        for side in ("team_a", "team_b"):
            team = teams[side]
            if team["roster"]["roster_id"] is None:
                missing.append(f"teams.{side}.roster")
            if team["team_strength"]["score"] is None:
                missing.append(f"teams.{side}.team_strength")
            if team["form"]["tournament_form_score"] is None:
                warnings.append(f"Tournament form unavailable for {side}.")
            if team["leadership"]["igl_score"] is None and team["leadership"]["coach_score"] is None:
                warnings.append(f"Leadership unavailable for {side}.")
        if not evidence_a:
            warnings.append("Recent series evidence unavailable for team_a.")
        if not evidence_b:
            warnings.append("Recent series evidence unavailable for team_b.")
        if h2h["organizations"]["maps_played"] == 0:
            warnings.append("Organization H2H is unavailable.")
        if h2h["current_rosters"]["maps_played"] == 0:
            warnings.append("Current rosters have no applicable H2H.")
        for item in maps:
            if item["team_a"]["sample_maps"] == 0 or item["team_b"]["sample_maps"] == 0:
                warnings.append(f"Map sample is incomplete for {item['map']}.")

    @staticmethod
    def _data_quality(missing: list[str], warnings: list[str], limitations: list[str]) -> dict:
        missing = list(dict.fromkeys(missing))
        warnings = list(dict.fromkeys(warnings))
        limitations = list(dict.fromkeys(limitations))
        critical = {"prediction", "matchup", "teams.team_a.roster", "teams.team_b.roster"}
        critical_missing = len(critical.intersection(missing))
        if critical_missing >= 3:
            status = "insufficient"
        elif critical_missing >= 1 or len(missing) >= 4:
            status = "weak"
        elif missing or warnings or limitations:
            status = "partial"
        else:
            status = "available"
        return {
            "overall_status": status,
            "limitations": limitations,
            "missing_sections": missing,
            "warnings": warnings,
        }
