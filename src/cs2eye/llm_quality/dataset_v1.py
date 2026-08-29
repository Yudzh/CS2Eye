"""Small curated regression dataset. It intentionally contains plans, not outcomes."""

from cs2eye.api.schemas.llm_quality import (
    LLMQualityCase, LLMQualityDataset, LLMQualityExpectations,
)
from cs2eye.api.schemas.match_explanation_plan import (
    ExplanationConclusion, ExplanationContradiction, ExplanationFact,
    ExplanationLimitation, ExplanationRisk, ExplanationSignal, MatchExplanationPlan,
    SupportingContext,
)


def _signal(identifier, side, category, direction, key, *, importance="high",
            reliability=.82, source="statistical"):
    return ExplanationSignal(
        signal_id=identifier, side=side, category=category, direction=direction,
        strength="moderate", importance=importance, reliability=reliability,
        sample_size=8, evidence_refs=[identifier.replace("signal:", "evidence:")],
        facts=[ExplanationFact(type="quality_fixture", text_key=key, values={
            "team": "G2" if side == "team_b" else "Aurora",
        })], source_kind=source,
    )


def _plan(*, favorite="team_b", advantage="small", confidence="medium",
          status="complete", advantages=(), counters=(), contradictions=(), risks=(),
          limitations=()):
    return MatchExplanationPlan(
        status=status,
        conclusion=ExplanationConclusion(
            favored_team=favorite, advantage=advantage, confidence=confidence,
            ml_probability_team_a=None if favorite == "none" else .45,
            ml_probability_team_b=None if favorite == "none" else .55,
        ),
        advantages=list(advantages), counter_arguments=list(counters),
        contradictions=list(contradictions), risks=list(risks),
        limitations=list(limitations),
        supporting_context=SupportingContext(
            team_a_name="Aurora", team_b_name="G2",
            tournament="CS2Eye Quality Cup", format="bo3",
        ),
    )


def _conflict():
    return ExplanationContradiction(
        contradiction_id="contradiction:ml_vs_matchup", category="ml_vs_matchup",
        importance="high", left_ref="prediction", right_ref="matchup",
        left_side="team_b", right_side="team_a",
        facts=[ExplanationFact(type="conflict", text_key="ml_vs_deterministic_matchup")],
    )


def _risk(identifier, key, *, severity="high", category="data_quality"):
    return ExplanationRisk(
        risk_id=identifier, category=category, severity=severity,
        evidence_refs=["data_quality"],
        facts=[ExplanationFact(type="risk", text_key=key)],
    )


def _limitation(identifier, key, *, severity="high", category="data_quality"):
    return ExplanationLimitation(
        limitation_id=identifier, category=category, severity=severity,
        evidence_refs=["data_quality"],
        facts=[ExplanationFact(type="limitation", text_key=key)],
    )


def _case(case_id, name, tags, plan, *, golden=False, forbidden=()):
    must_signals = [
        item.signal_id for item in (*plan.advantages, *plan.counter_arguments)
        if item.importance == "high"
    ]
    return LLMQualityCase(
        case_id=case_id, name=name, description=name,
        explanation_plan_snapshot=plan,
        expectations=LLMQualityExpectations(
            must_cover_signal_ids=must_signals,
            must_cover_contradiction_ids=[x.contradiction_id for x in plan.contradictions
                                          if x.importance == "high"],
            must_cover_risk_ids=[x.risk_id for x in plan.risks if x.severity == "high"],
            must_cover_limitation_ids=[x.limitation_id for x in plan.limitations
                                       if x.severity == "high"],
            forbidden_facts=list(forbidden),
            expected_favored_team=plan.conclusion.favored_team,
            expected_confidence=plan.conclusion.confidence,
        ), tags=tags, golden=golden,
    )


FORM_B = lambda: _signal("signal:recent_form:team_b", "team_b", "recent_form",
                         "supports_favorite", "strong_recent_form")
FORM_A = lambda: _signal("signal:recent_form:team_a", "team_a", "recent_form",
                         "against_favorite", "strong_recent_form")
MATCHUP_A = lambda: _signal("signal:matchup:overall:team_a", "team_a", "matchup",
                            "against_favorite", "matchup_disagrees", source="deterministic")
MAP_B = lambda: _signal("signal:map:dust2:team_b", "team_b", "map_pool",
                        "supports_favorite", "relevant_map_edge", source="deterministic")


def load_dataset_v1() -> LLMQualityDataset:
    cases = [
        _case("clear_favorite", "Явный фаворит без сильных возражений", ["clear_favorite"],
              _plan(advantage="clear", confidence="high", advantages=[FORM_B()])),
        _case("ml_55_45", "Небольшой перевес 55/45", ["close_match"],
              _plan(advantages=[FORM_B()])),
        _case("near_even", "Почти равный матч", ["close_match"],
              _plan(confidence="low", advantages=[_signal(
                  "signal:schedule:team_b", "team_b", "strength_of_schedule",
                  "supports_favorite", "small_schedule_edge", importance="medium")])) ,
        _case("slight_ml_matchup_conflict", "Небольшой конфликт ML и Matchup",
              ["ml_vs_matchup_conflict", "close_match"],
              _plan(confidence="low", counters=[MATCHUP_A()], contradictions=[_conflict()]),
              golden=True),
        _case("strong_ml_matchup_conflict", "Сильный конфликт ML и Matchup",
              ["ml_vs_matchup_conflict"],
              _plan(advantage="moderate", confidence="low", counters=[MATCHUP_A()],
                    contradictions=[_conflict()], risks=[_risk(
                        "risk:ml_matchup_disagreement", "ml_matchup_disagreement",
                        severity="medium", category="matchup")])) ,
        _case("strength_vs_tournament_form", "Общая сила против турнирной формы",
              ["strong_tournament_form"],
              _plan(advantages=[_signal("signal:strength:team_b", "team_b",
                                        "overall_strength", "supports_favorite", "overall_strength")],
                    counters=[_signal("signal:tournament_form:team_a", "team_a",
                                      "tournament_form", "against_favorite", "tournament_form")])) ,
        _case("form_weak_schedule", "Сильная форма на слабом расписании",
              ["strong_recent_form", "weak_schedule"],
              _plan(advantages=[FORM_B()], counters=[_signal(
                  "signal:schedule:team_a", "team_a", "strength_of_schedule",
                  "against_favorite", "weak_schedule")])) ,
        _case("recent_top_upset", "Недавняя победа над сильным соперником",
              ["strong_recent_form"], _plan(advantages=[_signal(
                  "signal:recent_upset:team_b", "team_b", "recent_form",
                  "supports_favorite", "win_vs_strong_opponent")])) ,
        _case("new_roster", "Новый нестабильный состав", ["new_roster"],
              _plan(confidence="low", risks=[_risk(
                  "risk:small_roster_sample:team_b", "small_roster_sample",
                  category="roster")]), golden=True),
        _case("no_current_h2h", "Нет встреч текущих составов", ["no_current_roster_h2h"],
              _plan(limitations=[_limitation(
                  "limitation:no_current_h2h", "no_current_roster_h2h", category="h2h")])) ,
        _case("old_org_h2h", "История организаций плохо применима",
              ["h2h_conflict"], _plan(limitations=[_limitation(
                  "limitation:old_org_h2h", "organization_h2h_low_applicability",
                  category="h2h")])) ,
        _case("strong_current_h2h", "Надёжный H2H текущих составов",
              ["h2h_conflict"], _plan(advantages=[_signal(
                  "signal:h2h:current:team_b", "team_b", "h2h",
                  "supports_favorite", "current_roster_h2h")])) ,
        _case("weak_map_sample", "Слабая выборка по карте", ["weak_map_sample"],
              _plan(risks=[_risk("risk:weak_map_sample", "weak_map_sample",
                                 category="map_pool")])) ,
        _case("no_veto", "Нет данных о veto", ["no_veto"],
              _plan(limitations=[_limitation("limitation:no_veto", "no_veto",
                                             category="veto")])) ,
        _case("relevant_map_advantage", "Преимущество на релевантной карте",
              ["map_advantage"], _plan(advantages=[MAP_B()])),
        _case("manual_positive", "Положительная ручная заметка", ["manual_context"],
              _plan(advantages=[_signal("signal:manual:positive", "team_b",
                  "manual_context", "supports_favorite", "analyst_note",
                  source="manual")]), golden=True),
        _case("manual_negative", "Негативная ручная заметка", ["manual_context"],
              _plan(counters=[_signal("signal:manual:negative", "team_a",
                  "manual_context", "against_favorite", "analyst_note",
                  source="manual")])) ,
        _case("mixed_manual_statistical", "Статистика вместе с ручным контекстом",
              ["manual_context", "strong_recent_form"],
              _plan(advantages=[FORM_B(), _signal("signal:manual:positive", "team_b",
                  "manual_context", "supports_favorite", "analyst_note",
                  importance="medium", source="manual")])) ,
        _case("weak_data", "Слабое качество данных", ["weak_data"],
              _plan(status="limited", confidence="low", risks=[_risk(
                  "risk:weak_data_quality", "weak_data_quality")], limitations=[_limitation(
                  "limitation:partial_data", "partial_data")]), golden=True),
        _case("insufficient_data", "Недостаточно данных", ["insufficient_data"],
              _plan(favorite="none", advantage="none", confidence="insufficient",
                    status="insufficient_data", limitations=[_limitation(
                        "limitation:insufficient_data", "insufficient_data")]), golden=True),
    ]
    return LLMQualityDataset(cases=cases)


DATASET_V1 = load_dataset_v1()
