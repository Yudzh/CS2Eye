from dataclasses import dataclass

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan import (
    ExplanationConclusion, ExplanationContradiction, ExplanationFact,
    ExplanationLimitation, ExplanationRisk, ExplanationSignal, MatchExplanationPlan,
    SupportingContext,
)
from cs2eye.services.match_explanation_rules import (
    MAX_ADVANTAGES, MAX_CONTRADICTIONS, MAX_COUNTER_ARGUMENTS, MAX_RISKS,
    MIN_FACTOR_DISTANCE, MIN_FORM_SAMPLE, MIN_H2H_RELIABILITY, MIN_H2H_SAMPLE,
    MIN_MAP_RELIABILITY, MIN_MAP_SAMPLE, MIN_SIGNAL_RELIABILITY,
    confidence_level, probability_advantage, score_side, signal_strength,
)


@dataclass(frozen=True)
class _Candidate:
    signal: ExplanationSignal
    distance: float
    priority: int


class DeterministicMatchExplanationBuilder:
    """Pure context -> plan transformation. No I/O, time, randomness, or LLM."""

    def build(self, context: MatchAnalysisContext) -> MatchExplanationPlan:
        prediction = context.prediction
        favorite = self._favorite(context)
        matchup_side = score_side(context.matchup.team_a_score, neutral=False)
        conflict = bool(
            favorite in {"team_a", "team_b"}
            and matchup_side is not None
            and matchup_side != favorite
            and (context.matchup.reliability or 0) >= MIN_SIGNAL_RELIABILITY
        )
        quality = context.data_quality.overall_status
        candidates = self._signals(context, favorite)
        relevant_reliabilities = sorted(
            (item.signal.reliability for item in candidates), reverse=True,
        )[:5]
        factor_reliability = (
            sum(relevant_reliabilities) / len(relevant_reliabilities)
            if relevant_reliabilities else (prediction.confidence or 0)
        )
        confidence = confidence_level(
            min(prediction.confidence or 0, factor_reliability),
            quality, conflict=conflict,
        )
        status = (
            "insufficient_data" if quality == "insufficient"
            else "limited" if quality in {"weak", "partial"} else "complete"
        )
        conclusion = ExplanationConclusion(
            favored_team=favorite,
            advantage=probability_advantage(
                prediction.team_a_probability, prediction.team_b_probability,
            ),
            confidence=confidence,
            ml_probability_team_a=prediction.team_a_probability,
            ml_probability_team_b=prediction.team_b_probability,
        )
        advantages = self._select(
            [item for item in candidates if item.signal.direction == "supports_favorite"],
            MAX_ADVANTAGES,
        )
        counters = self._select(
            [item for item in candidates if item.signal.direction == "against_favorite"],
            MAX_COUNTER_ARGUMENTS,
        )
        contradictions = self._contradictions(context, favorite, conflict)
        limitations = self._limitations(context)
        risks = self._risks(context, conflict)
        return MatchExplanationPlan(
            status=status, conclusion=conclusion,
            advantages=advantages, counter_arguments=counters,
            contradictions=contradictions[:MAX_CONTRADICTIONS],
            risks=risks[:MAX_RISKS], limitations=limitations,
            supporting_context=SupportingContext(
                team_a_name=context.teams.team_a.name,
                team_b_name=context.teams.team_b.name,
                tournament=context.match.tournament.name,
                format=context.match.format,
            ),
        )

    @staticmethod
    def _favorite(context) -> str:
        prediction = context.prediction
        if (
            prediction.status != "available"
            or prediction.team_a_probability is None
            or prediction.team_b_probability is None
            or prediction.team_a_probability == prediction.team_b_probability
        ):
            return "none"
        return (
            "team_a" if prediction.team_a_probability > prediction.team_b_probability
            else "team_b"
        )

    def _signals(self, context, favorite) -> list[_Candidate]:
        if favorite == "none":
            return []
        result: list[_Candidate] = []
        a, b = context.teams.team_a, context.teams.team_b

        def add(
            identifier, side, category, score_a, reliability, sample, refs, fact_type,
            text_key, values, source="statistical", priority=3,
        ):
            if score_a is None or reliability is None:
                return
            distance = abs(float(score_a) - 50)
            if reliability < MIN_SIGNAL_RELIABILITY or distance < MIN_FACTOR_DISTANCE:
                return
            direction = "supports_favorite" if side == favorite else "against_favorite"
            result.append(_Candidate(ExplanationSignal(
                signal_id=identifier, side=side, category=category,
                direction=direction, strength=signal_strength(distance),
                importance="high" if reliability >= .75 and distance >= 8 else "medium",
                reliability=reliability, sample_size=sample, evidence_refs=refs,
                facts=[ExplanationFact(type=fact_type, text_key=text_key, values=values)],
                source_kind=source,
            ), distance, priority))

        # Pairwise team-level factors.
        team_pairs = (
            ("overall_strength", a.team_strength.score, b.team_strength.score,
             min(a.team_strength.reliability, b.team_strength.reliability),
             min(a.team_strength.sample_size, b.team_strength.sample_size), 1),
            ("recent_form", a.form.recent_60d_score, b.form.recent_60d_score,
             min(a.form.recent_60d_reliability, b.form.recent_60d_reliability),
             min(a.form.recent_60d_matches, b.form.recent_60d_matches), 1),
            ("tournament_form", a.form.tournament_form_score, b.form.tournament_form_score,
             min(a.form.tournament_reliability, b.form.tournament_reliability),
             min(a.form.tournament_matches, b.form.tournament_matches), 1),
            ("strength_of_schedule", a.form.strength_of_schedule_score,
             b.form.strength_of_schedule_score,
             min(a.form.recent_60d_reliability, b.form.recent_60d_reliability),
             min(a.form.recent_60d_matches, b.form.recent_60d_matches), 2),
            ("performance_vs_expectation", a.form.performance_vs_expectation_score,
             b.form.performance_vs_expectation_score,
             min(a.form.recent_60d_reliability, b.form.recent_60d_reliability),
             min(a.form.recent_60d_matches, b.form.recent_60d_matches), 2),
            ("roster", a.roster.stability_score, b.roster.stability_score,
             min(a.roster.reliability, b.roster.reliability),
             min(a.roster.sample_maps, b.roster.sample_maps), 2),
            ("leadership", a.leadership.igl_score, b.leadership.igl_score,
             min(a.leadership.reliability, b.leadership.reliability),
             min(a.leadership.sample_size, b.leadership.sample_size), 4),
        )
        for category, value_a, value_b, reliability, sample, priority in team_pairs:
            if value_a is None or value_b is None:
                continue
            if category in {"recent_form", "tournament_form", "strength_of_schedule",
                            "performance_vs_expectation"} and sample < MIN_FORM_SAMPLE:
                continue
            pair_score = 50 + (float(value_a) - float(value_b)) / 2
            side = score_side(pair_score, neutral=False)
            if side:
                team = a if side == "team_a" else b
                add(
                    f"signal:{category}:{side}", side, category, pair_score,
                    reliability, sample,
                    [f"team:{a.id}:form" if category not in {"overall_strength", "roster", "leadership"}
                     else f"team:{a.id}:{'strength' if category == 'overall_strength' else category}",
                     f"team:{b.id}:form" if category not in {"overall_strength", "roster", "leadership"}
                     else f"team:{b.id}:{'strength' if category == 'overall_strength' else category}"],
                    "team_comparison", f"{category}_edge",
                    {"team": team.name, "team_a_value": value_a, "team_b_value": value_b},
                    priority=priority,
                )

        # The aggregate deterministic matchup is the direct analytical
        # counterpoint to ML. Preserve even a small >50 disagreement: its
        # meaning is the disagreement itself, not a claim of a large edge.
        matchup_side = score_side(context.matchup.team_a_score, neutral=False)
        if (
            matchup_side is not None
            and matchup_side != favorite
            and context.matchup.reliability >= MIN_SIGNAL_RELIABILITY
        ):
            result.append(_Candidate(ExplanationSignal(
                signal_id=f"signal:matchup:overall:{matchup_side}",
                side=matchup_side, category="matchup", direction="against_favorite",
                strength=signal_strength(abs(context.matchup.team_a_score - 50)),
                importance="high", reliability=context.matchup.reliability,
                sample_size=None, evidence_refs=["matchup"],
                facts=[ExplanationFact(
                    type="matchup", text_key="deterministic_matchup_disagrees_with_ml",
                    values={
                        "team": getattr(context.teams, matchup_side).name,
                        "team_a_score": context.matchup.team_a_score,
                        "team_b_score": context.matchup.team_b_score,
                    },
                )], source_kind="deterministic",
            ), abs(context.matchup.team_a_score - 50), 0))

        # Matchup components are already pairwise 0..100.
        for factor in context.matchup.factors:
            # H2H has stricter applicability/reliability rules below. The
            # aggregate matchup component must not bypass those rules.
            if factor.key == "h2h":
                continue
            side = score_side(factor.team_a_score, neutral=False)
            if side:
                category = self._factor_category(factor.key)
                add(
                    f"signal:matchup:{factor.key}:{side}", side, category,
                    factor.team_a_score, factor.reliability, factor.sample_size,
                    [factor.factor_id], "matchup_factor", "factor_edge",
                    {"factor": factor.key, "team": getattr(context.teams, side).name},
                    source="deterministic", priority=3,
                )

        # Relevant map signals; exclude tiny or unreliable samples.
        for map_item in context.map_matchups:
            reliability = min(map_item.team_a.reliability, map_item.team_b.reliability)
            sample = min(map_item.team_a.sample_maps, map_item.team_b.sample_maps)
            if reliability < MIN_MAP_RELIABILITY or sample < MIN_MAP_SAMPLE:
                continue
            seen_sides = set()
            for edge in map_item.key_edges:
                if edge.reliability < MIN_MAP_RELIABILITY or edge.favored_team in seen_sides:
                    continue
                seen_sides.add(edge.favored_team)
                side = edge.favored_team
                distance = {"small": 4, "moderate": 9, "clear": 16}[edge.strength]
                add(
                    f"signal:map:{map_item.map}:{edge.metric}:{side}", side,
                    self._factor_category(edge.metric), 50 + distance if side == "team_a" else 50 - distance,
                    edge.reliability, sample, [edge.evidence_id], "map_edge", "map_edge",
                    {"team": getattr(context.teams, side).name, "map": map_item.map,
                     "metric": edge.metric, "strength": edge.strength},
                    source="deterministic", priority=2,
                )

        # Current-roster H2H is preferred. Organization history is explanatory only
        # when explicitly applicable and no reliable current-roster sample exists.
        current = context.h2h.current_rosters
        organization = context.h2h.organizations
        h2h_scope = None
        h2h_ref = None
        if (
            current.team_a_rating is not None
            and (current.confidence or 0) >= MIN_H2H_RELIABILITY
            and current.series_played >= MIN_H2H_SAMPLE
        ):
            h2h_scope, h2h_ref = current, "h2h:current_rosters"
        elif (
            context.h2h.history_applicability in {"high", "medium"}
            and organization.team_a_rating is not None
            and (organization.confidence or 0) >= MIN_H2H_RELIABILITY
            and organization.series_played >= MIN_H2H_SAMPLE
        ):
            h2h_scope, h2h_ref = organization, "h2h:organizations"
        if h2h_scope is not None:
            side = score_side(h2h_scope.team_a_rating, neutral=False)
            if side:
                add(
                    f"signal:h2h:{h2h_ref.split(':')[-1]}:{side}", side, "h2h",
                    h2h_scope.team_a_rating, h2h_scope.confidence,
                    h2h_scope.series_played, [h2h_ref], "h2h", "h2h_edge",
                    {"team": getattr(context.teams, side).name,
                     "scope": h2h_ref.split(":")[-1]}, priority=4,
                )

        # Manual notes are directionally classified but never blended into reliability.
        for side in ("team_a", "team_b"):
            for note in getattr(context.manual_context, side):
                if note.polarity == "neutral":
                    continue
                note_side = side if note.polarity == "positive" else (
                    "team_b" if side == "team_a" else "team_a"
                )
                direction = "supports_favorite" if note_side == favorite else "against_favorite"
                result.append(_Candidate(ExplanationSignal(
                    signal_id=f"signal:manual:{note.note_id}", side=note_side,
                    category="manual_context", direction=direction, strength="small",
                    importance="low", reliability=0.5, sample_size=None,
                    evidence_refs=[note.note_id],
                    facts=[ExplanationFact(type="manual_note", text_key="analyst_note", values={
                        "subject_team": getattr(context.teams, side).name,
                        "polarity": note.polarity, "text": note.text,
                    })], source_kind="manual",
                ), 3, 5))
        return result

    @staticmethod
    def _select(candidates, limit):
        # Prefer relevance/reliability/magnitude and avoid near-duplicate categories.
        ordered = sorted(
            candidates,
            key=lambda item: (item.priority, -item.signal.reliability, -item.distance,
                              item.signal.signal_id),
        )
        selected, per_category = [], {}
        for candidate in ordered:
            category = candidate.signal.category
            if per_category.get(category, 0) >= (2 if category == "map_pool" else 1):
                continue
            selected.append(candidate.signal)
            per_category[category] = per_category.get(category, 0) + 1
            if len(selected) == limit:
                break
        return selected

    @staticmethod
    def _factor_category(key):
        return {
            "team_strength": "overall_strength", "form_context": "recent_form",
            "current_roster_form": "roster", "map_veto": "veto",
            "tactical_matchup": "map_pool", "h2h": "h2h",
            "leadership_context": "leadership", "side": "map_pool",
            "bomb": "postplant", "combat_swing": "opening", "economy": "economy",
            "utility": "map_pool", "trading": "trade", "pistol": "map_pool",
            "full_buy": "economy", "force_buy": "economy", "anti_eco": "economy",
        }.get(key, key if key in {"ct_side", "t_side", "opening", "trade", "clutch",
                                  "postplant", "retake"} else "map_pool")

    def _contradictions(self, context, favorite, ml_matchup_conflict):
        result = []
        matchup_side = score_side(context.matchup.team_a_score, neutral=False)
        if ml_matchup_conflict and matchup_side:
            result.append(ExplanationContradiction(
                contradiction_id="contradiction:ml_vs_matchup",
                category="ml_vs_matchup", importance="high", left_ref="prediction",
                right_ref="matchup", left_side=favorite, right_side=matchup_side,
                facts=[ExplanationFact(
                    type="conflict", text_key="ml_vs_deterministic_matchup",
                    values={
                        "ml_side": favorite,
                        "matchup_side": matchup_side,
                        "team_a_name": context.teams.team_a.name,
                        "team_b_name": context.teams.team_b.name,
                    },
                )],
            ))
        # Overall strength vs reliable recent/tournament form.
        a, b = context.teams.team_a, context.teams.team_b
        strength_side = (
            score_side(50 + (a.team_strength.score - b.team_strength.score) / 2, neutral=False)
            if a.team_strength.score is not None and b.team_strength.score is not None
            else None
        )
        for key, va, vb, rel in (
            ("recent", a.form.recent_60d_score, b.form.recent_60d_score,
             min(a.form.recent_60d_reliability or 0, b.form.recent_60d_reliability or 0)),
            ("tournament", a.form.tournament_form_score, b.form.tournament_form_score,
             min(a.form.tournament_reliability or 0, b.form.tournament_reliability or 0)),
        ):
            if va is None or vb is None or rel < MIN_SIGNAL_RELIABILITY:
                continue
            strength_distance = abs(a.team_strength.score - b.team_strength.score) / 2
            form_distance = abs(va - vb) / 2
            form_side = score_side(50 + (va - vb) / 2, neutral=False)
            if (
                strength_distance >= MIN_FACTOR_DISTANCE
                and form_distance >= MIN_FACTOR_DISTANCE
                and strength_side and form_side and strength_side != form_side
            ):
                result.append(ExplanationContradiction(
                    contradiction_id=f"contradiction:strength_vs_{key}_form",
                    category="strength_vs_form", importance="medium",
                    left_ref="matchup:team_strength",
                    right_ref=f"team:{a.id}:form", left_side=strength_side,
                    right_side=form_side,
                    facts=[ExplanationFact(
                        type="conflict", text_key="overall_strength_vs_form",
                        values={"form_scope": key},
                    )],
                ))
                break
        organization = context.h2h.organizations
        current = context.h2h.current_rosters
        if (
            context.h2h.history_applicability in {"high", "medium"}
            and organization.team_a_rating is not None
            and current.team_a_rating is not None
            and (organization.confidence or 0) >= MIN_H2H_RELIABILITY
            and (current.confidence or 0) >= MIN_H2H_RELIABILITY
            and organization.series_played >= MIN_H2H_SAMPLE
            and current.series_played >= MIN_H2H_SAMPLE
        ):
            organization_side = score_side(organization.team_a_rating, neutral=False)
            current_side = score_side(current.team_a_rating, neutral=False)
            if organization_side and current_side and organization_side != current_side:
                result.append(ExplanationContradiction(
                    contradiction_id="contradiction:organization_vs_roster_h2h",
                    category="organization_vs_roster_h2h", importance="medium",
                    left_ref="h2h:organizations", right_ref="h2h:current_rosters",
                    left_side=organization_side, right_side=current_side,
                    facts=[ExplanationFact(
                        type="conflict", text_key="organization_vs_current_roster_h2h",
                    )],
                ))
        map_factor = next(
            (item for item in context.matchup.factors if item.key == "map_veto"), None,
        )
        reliable_maps = [
            item for item in context.map_matchups
            if item.matchup_score_team_a is not None
            and min(item.team_a.reliability, item.team_b.reliability) >= MIN_MAP_RELIABILITY
            and min(item.team_a.sample_maps, item.team_b.sample_maps) >= MIN_MAP_SAMPLE
        ]
        if map_factor and (map_factor.reliability or 0) >= MIN_MAP_RELIABILITY and reliable_maps:
            total = sum(item.relevance or 0 for item in reliable_maps)
            relevant_score = (
                sum(item.matchup_score_team_a * (item.relevance or 0) for item in reliable_maps) / total
                if total else sum(item.matchup_score_team_a for item in reliable_maps) / len(reliable_maps)
            )
            overall_side = score_side(map_factor.team_a_score, neutral=False)
            relevant_side = score_side(relevant_score, neutral=False)
            if overall_side and relevant_side and overall_side != relevant_side:
                result.append(ExplanationContradiction(
                    contradiction_id="contradiction:overall_vs_relevant_maps",
                    category="overall_vs_relevant_maps", importance="medium",
                    left_ref=map_factor.factor_id,
                    right_ref=f"map:{reliable_maps[0].map}",
                    left_side=overall_side, right_side=relevant_side,
                    facts=[ExplanationFact(
                        type="conflict", text_key="overall_map_profile_vs_relevant_maps",
                    )],
                ))
        return result

    @staticmethod
    def _risks(context, conflict):
        risks = []
        if conflict:
            risks.append(ExplanationRisk(
                risk_id="risk:ml_matchup_disagreement", category="other", severity="medium",
                evidence_refs=["prediction", "matchup"],
                facts=[ExplanationFact(type="conflict", text_key="ml_matchup_disagreement")],
            ))
        for side in ("team_a", "team_b"):
            team = getattr(context.teams, side)
            if team.roster.sample_maps < 10 or team.roster.reliability < .6:
                risks.append(ExplanationRisk(
                    risk_id=f"risk:small_roster_sample:{side}", category="roster",
                    severity="medium", evidence_refs=[f"team:{team.id}:roster"],
                    facts=[ExplanationFact(type="sample", text_key="small_roster_sample",
                                           values={"team": team.name, "maps": team.roster.sample_maps})],
                ))
        if context.data_quality.overall_status == "weak":
            risks.append(ExplanationRisk(
                risk_id="risk:weak_data_quality", category="data_quality", severity="high",
                evidence_refs=["data_quality"],
                facts=[ExplanationFact(type="quality", text_key="weak_data_quality")],
            ))
        return risks

    @staticmethod
    def _limitations(context):
        result = []
        messages = [*context.data_quality.limitations, *context.data_quality.warnings]
        for index, message in enumerate(messages):
            lowered = message.lower()
            category = "veto" if "veto" in lowered else "h2h" if "h2h" in lowered else (
                "tournament_form" if "tournament form" in lowered else "data_quality"
            )
            slug = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")[:48]
            result.append(ExplanationLimitation(
                limitation_id=f"limitation:{slug or index}", category=category,
                severity="high" if context.data_quality.overall_status in {"weak", "insufficient"}
                else "medium", evidence_refs=["data_quality"],
                facts=[ExplanationFact(type="limitation", text_key="data_unavailable",
                                       values={"code": message})],
            ))
        for section in context.data_quality.missing_sections:
            result.append(ExplanationLimitation(
                limitation_id=f"limitation:missing:{section}", category="data_quality",
                severity="high", evidence_refs=["data_quality"],
                facts=[ExplanationFact(type="limitation", text_key="missing_section",
                                       values={"section": section})],
            ))
        return result
