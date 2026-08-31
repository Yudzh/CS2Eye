from collections import defaultdict

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan_v2 import (
    ExpectedWinner, FixedConclusion, FixedManualNote, FormComparison, FormEvidence, KeyMapEdge,
    ManualContextSection, MapEdgeReason, MapProfileItem, MapsSection,
    MatchExplanationPlanV2, PreviousTournamentFallback, TeamMapProfile,
    TeamplaySection, TeamplaySignal, TournamentFormSection, TournamentFormTeam,
)
from cs2eye.services.match_explanation_rules import confidence_level, probability_advantage


MIN_MAP_SAMPLE = 3
MIN_MAP_RELIABILITY = .60
STRONG_MAP_SCORE = 55
WEAK_MAP_SCORE = 45
MIN_TEAMPLAY_RELIABILITY = .60


class DeterministicMatchExplanationBuilderV2:
    """Pure context -> fixed five-section plan transformation."""

    def build(self, context: MatchAnalysisContext) -> MatchExplanationPlanV2:
        favorite = self._favorite(context)
        return MatchExplanationPlanV2(
            expected_winner=self._expected_winner(context, favorite),
            conclusion=self._conclusion(context, favorite),
            form=self._form(context),
            maps=self._maps(context),
            teamplay=self._teamplay(context),
            manual_context=self._manual(context),
        )

    @staticmethod
    def _favorite(context: MatchAnalysisContext) -> str:
        prediction = context.prediction
        if (
            prediction.status != "available"
            or prediction.team_a_probability is None
            or prediction.team_b_probability is None
            or prediction.team_a_probability == prediction.team_b_probability
        ):
            return "none"
        return "team_a" if prediction.team_a_probability > prediction.team_b_probability else "team_b"

    @staticmethod
    def _expected_winner(
        context: MatchAnalysisContext, favorite: str,
    ) -> ExpectedWinner | None:
        if favorite not in {"team_a", "team_b"}:
            return None
        team = getattr(context.teams, favorite)
        probability = getattr(context.prediction, f"{favorite}_probability")
        if team.id is None or team.name is None or probability is None:
            return None
        return ExpectedWinner(
            team_id=team.id, team_name=team.name, win_probability=probability,
        )

    def _conclusion(self, context, favorite) -> FixedConclusion:
        prediction = context.prediction
        quality = context.data_quality.overall_status
        reliability = prediction.confidence or 0
        return FixedConclusion(
            team_a_name=context.teams.team_a.name or "team_a",
            team_b_name=context.teams.team_b.name or "team_b",
            favored_team=favorite,
            favored_team_name=(
                context.teams.team_a.name if favorite == "team_a"
                else context.teams.team_b.name if favorite == "team_b" else None
            ),
            advantage=probability_advantage(
                prediction.team_a_probability, prediction.team_b_probability,
            ),
            confidence=confidence_level(reliability, quality, conflict=False),
            ml_probability_team_a=prediction.team_a_probability,
            ml_probability_team_b=prediction.team_b_probability,
            internal_statistics_disclaimer=(
                "Преимущество основано на внутренней статистике CS2Eye. "
                "Форма на текущем турнире рассматривается отдельно от общей статистики."
            ),
        )

    def _form(self, context) -> TournamentFormSection:
        a_matches = context.teams.team_a.form.tournament_matches
        b_matches = context.teams.team_b.form.tournament_matches
        if a_matches and b_matches:
            state = "current_tournament"
        elif not a_matches and not b_matches:
            state = "not_started" if context.match.tournament.id else "fallback"
        else:
            state = "mixed_availability"
        team_a = self._form_team(context, "team_a", state)
        team_b = self._form_team(context, "team_b", state)
        score_a = team_a.score
        score_b = team_b.score
        if score_a is None or score_b is None or abs(score_a - score_b) < 3:
            side, strength = "none", "none"
        else:
            side = "team_a" if score_a > score_b else "team_b"
            distance = abs(score_a - score_b)
            strength = "clear" if distance >= 20 else "moderate" if distance >= 10 else "small"
        notes = []
        if state == "not_started":
            notes.append("Турнир только начинается, поэтому команды ещё не сформировали турнирную форму.")
        elif state == "mixed_availability":
            notes.append("Турнирная форма команд основана на неодинаковом числе матчей и напрямую не сопоставима.")
        elif state == "fallback":
            notes.append("Текущий турнир не задан; используется последний доступный релевантный контекст.")
        if team_a.fallback == "recent_60d" or team_b.fallback == "recent_60d":
            notes.append("Для команды без данных завершённого турнира используется недавняя форма как явно отмеченный fallback.")
        if team_a.fallback == "insufficient" or team_b.fallback == "insufficient":
            notes.append("Для одной или обеих команд недостаточно надёжных данных о форме.")
        return TournamentFormSection(
            state=state, team_a=team_a, team_b=team_b,
            comparison=FormComparison(
                favored_team=side,
                favored_team_name=(team_a.team_name if side == "team_a" else team_b.team_name if side == "team_b" else None),
                strength=strength,
            ),
            context_notes=notes,
        )

    def _form_team(self, context, side: str, state: str) -> TournamentFormTeam:
        team = getattr(context.teams, side)
        evidence = list(getattr(context.recent_series_evidence, side))
        current = [item for item in evidence if item.current_tournament]
        use_current = team.form.tournament_matches > 0
        previous = None
        fallback = "none"
        selected = current if use_current else []
        score = team.form.tournament_form_score if use_current else None
        reliability = team.form.tournament_reliability if use_current else None
        matches = team.form.tournament_matches if use_current else 0
        if not use_current:
            previous = self._previous_tournament(evidence)
            if previous:
                fallback = "previous_tournament"
                selected = []
                matches = previous.matches
                results = [item.result for item in previous.evidence if item.result]
                score = 50 + 50 * ((results.count("win") - results.count("loss")) / len(results)) if results else None
                reliability = min(1.0, matches / 5)
            elif team.form.recent_60d_score is not None:
                fallback = "recent_60d"
                score = team.form.recent_60d_score
                reliability = team.form.recent_60d_reliability
                matches = team.form.recent_60d_matches
            else:
                fallback = "insufficient"
        return TournamentFormTeam(
            team_name=team.name or side,
            form_level=self._form_level(score), reliability=reliability,
            matches=matches, score=score,
            performance_vs_expectation=team.form.performance_vs_expectation_score,
            evidence=[self._form_evidence(item) for item in selected],
            previous_tournament=previous, fallback=fallback,
        )

    def _previous_tournament(self, evidence) -> PreviousTournamentFallback | None:
        groups = defaultdict(list)
        for item in evidence:
            if not item.current_tournament and item.tournament:
                groups[item.tournament].append(item)
        if not groups:
            return None
        tournament, rows = max(
            groups.items(), key=lambda pair: max((item.date for item in pair[1] if item.date), default=context_date_min()),
        )
        ordered = sorted(rows, key=lambda item: (item.date or context_date_min(), item.evidence_id))
        return PreviousTournamentFallback(
            tournament=tournament, matches=len(ordered),
            evidence=[self._form_evidence(item) for item in ordered],
        )

    @staticmethod
    def _form_evidence(item) -> FormEvidence:
        return FormEvidence(
            evidence_id=item.evidence_id,
            date=item.date.isoformat() if item.date else None,
            tournament=item.tournament, opponent=item.opponent.name,
            opponent_rank=item.opponent.rank, result=item.result,
            series_score=item.series_score,
            performance_vs_expectation=item.performance_vs_expectation,
        )

    @staticmethod
    def _form_level(score):
        if score is None: return "unknown"
        if score >= 70: return "strong"
        if score >= 55: return "good"
        if score >= 45: return "mixed"
        return "weak"

    def _maps(self, context) -> MapsSection:
        profiles = {}
        for side in ("team_a", "team_b"):
            rows = []
            for item in context.map_matchups:
                data = getattr(item, side)
                if data.map_strength is None or data.reliability is None:
                    continue
                if data.sample_maps < MIN_MAP_SAMPLE or data.reliability < MIN_MAP_RELIABILITY:
                    continue
                classification = "strong" if data.map_strength >= STRONG_MAP_SCORE else "weak" if data.map_strength <= WEAK_MAP_SCORE else None
                if classification:
                    rows.append(MapProfileItem(
                        map=item.map, strength_score=data.map_strength,
                        reliability=data.reliability, sample_maps=data.sample_maps,
                        classification=classification,
                    ))
            profiles[side] = TeamMapProfile(
                team_name=getattr(context.teams, side).name or side,
                strong_maps=sorted((x for x in rows if x.classification == "strong"), key=lambda x: (-x.strength_score, x.map))[:3],
                weak_maps=sorted((x for x in rows if x.classification == "weak"), key=lambda x: (x.strength_score, x.map))[:3],
            )
        edges = []
        for item in sorted(context.map_matchups, key=lambda x: (-(x.relevance or 0), x.map)):
            if item.matchup_score_team_a is None or abs(item.matchup_score_team_a - 50) < 3:
                continue
            side = "team_a" if item.matchup_score_team_a > 50 else "team_b"
            distance = abs(item.matchup_score_team_a - 50)
            strength = "clear" if distance >= 12 else "moderate" if distance >= 7 else "small"
            reasons = self._map_reasons(item, side)
            if reasons:
                edges.append(KeyMapEdge(
                    map=item.map, favored_team=side,
                    favored_team_name=getattr(context.teams, side).name or side,
                    strength=strength,
                    relevance=item.relevance, reasons=reasons[:5],
                ))
            if len(edges) == 3: break
        status = "available" if any((profiles["team_a"].strong_maps, profiles["team_a"].weak_maps, profiles["team_b"].strong_maps, profiles["team_b"].weak_maps, edges)) else "insufficient"
        notes = [] if status == "available" else ["Недостаточно надёжных данных для уверенного сравнения карт."]
        return MapsSection(status=status, team_a=profiles["team_a"], team_b=profiles["team_b"], key_map_edges=edges, context_notes=notes)

    def _map_reasons(self, item, favored_side):
        reasons = []
        own = getattr(item, favored_side)
        other_side = "team_b" if favored_side == "team_a" else "team_a"
        opponent = getattr(item, other_side)
        if own.sample_maps < MIN_MAP_SAMPLE:
            reasons.append(MapEdgeReason(type="team_low_sample", side=favored_side, side_name=favored_side, strength="small", reliability=own.reliability))
        elif own.map_strength is not None and own.map_strength >= STRONG_MAP_SCORE:
            reasons.append(MapEdgeReason(type="team_strong_on_map", side=favored_side, side_name=favored_side, strength="moderate", reliability=own.reliability))
        if opponent.sample_maps < MIN_MAP_SAMPLE:
            reasons.append(MapEdgeReason(type="opponent_low_sample", side=other_side, side_name=other_side, strength="small", reliability=opponent.reliability))
        elif opponent.map_strength is not None and opponent.map_strength <= WEAK_MAP_SCORE:
            reasons.append(MapEdgeReason(type="opponent_weak_on_map", side=other_side, side_name=other_side, strength="moderate", reliability=opponent.reliability))
        mapping = {"trade": "trading", "trading": "trading"}
        allowed = {"ct_side", "t_side", "opening", "trading", "clutch", "postplant", "retake", "full_buy", "force_buy", "anti_eco", "pistol", "utility"}
        for edge in item.key_edges:
            metric = mapping.get(edge.metric, edge.metric)
            if (
                edge.favored_team == favored_side and metric in allowed
                and (edge.reliability or 0) >= MIN_MAP_RELIABILITY
            ):
                reasons.append(MapEdgeReason(
                    type=metric, side=favored_side, side_name=favored_side, strength=edge.strength,
                    reliability=edge.reliability, evidence_id=edge.evidence_id,
                ))
        return reasons

    def _teamplay(self, context) -> TeamplaySection:
        category_map = {"trade": "trading", "trading": "trading"}
        allowed = {"ct_side", "t_side", "opening", "trading", "clutch", "postplant", "retake", "pistol", "force_buy", "full_buy", "anti_eco", "utility"}
        candidates = []
        for item in context.map_matchups:
            for edge in item.key_edges:
                category = category_map.get(edge.metric, edge.metric)
                reliability = edge.reliability or 0
                if category not in allowed or reliability < MIN_TEAMPLAY_RELIABILITY or edge.strength == "small":
                    continue
                candidates.append(TeamplaySignal(
                    signal_id=f"teamplay:{item.map}:{category}:{edge.favored_team}",
                    category=category, side=edge.favored_team,
                    side_name=getattr(context.teams, edge.favored_team).name or edge.favored_team,
                    effect="positive",
                    strength=edge.strength, reliability=reliability,
                    fact_type=f"strong_{category}", map=item.map,
                    evidence_id=edge.evidence_id,
                ))
        rank = {"clear": 2, "moderate": 1, "small": 0}
        ordered = sorted(candidates, key=lambda x: (-rank[x.strength], -x.reliability, x.signal_id))
        selected, seen = [], set()
        for item in ordered:
            key = (item.category, item.side)
            if key in seen: continue
            selected.append(item); seen.add(key)
            if len(selected) == 5: break
        notes = [] if selected else ["Надёжных выраженных различий по доступным teamplay/swing показателям не найдено."]
        return TeamplaySection(signals=selected, context_notes=notes)

    @staticmethod
    def _manual(context) -> ManualContextSection:
        def convert(side):
            team = getattr(context.teams, side)
            return [FixedManualNote(
                note_id=item.note_id, team_name=team.name or side,
                polarity=item.polarity, players=item.players, coach=item.coach,
                map=item.map, text=item.text,
            ) for item in getattr(context.manual_context, side)]
        a, b = convert("team_a"), convert("team_b")
        return ManualContextSection(
            team_a=a, team_b=b,
            empty_message=None if a or b else "Ручных комментариев по этому матчу нет.",
        )


def context_date_min():
    from datetime import date
    return date.min
