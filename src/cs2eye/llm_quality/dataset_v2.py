"""Small curated regression dataset for the v2 plan / v5 prompt / v3 analysis pipeline.

It intentionally contains fixed MatchExplanationPlanV2 snapshots, not outcomes.
"""

from cs2eye.api.schemas.llm_quality import (
    LLMQualityCase, LLMQualityDataset, LLMQualityExpectations,
)
from cs2eye.api.schemas.match_explanation_plan_v2 import (
    ExpectedWinner, FixedConclusion, FixedManualNote, FormComparison, FormEvidence,
    KeyMapEdge, ManualContextSection, MapEdgeReason, MapProfileItem, MapsSection,
    MatchExplanationPlanV2, PreviousTournamentFallback, TeamMapProfile,
    TeamplaySection, TeamplaySignal, TournamentFormSection, TournamentFormTeam,
)


TEAM_A, TEAM_B = "Aurora", "G2"


def _name(side):
    return TEAM_A if side == "team_a" else TEAM_B


def _expected_winner(favorite="team_b", probability=.58):
    if favorite == "none":
        return None
    return ExpectedWinner(
        team_id=9 if favorite == "team_b" else 8, team_name=_name(favorite),
        win_probability=probability,
    )


def _conclusion(*, favorite="team_b", advantage="small", confidence="medium",
                prob_a=.42, prob_b=.58):
    return FixedConclusion(
        team_a_name=TEAM_A, team_b_name=TEAM_B, favored_team=favorite,
        favored_team_name=_name(favorite) if favorite in {"team_a", "team_b"} else None,
        advantage=advantage, confidence=confidence,
        ml_probability_team_a=prob_a if favorite != "none" else None,
        ml_probability_team_b=prob_b if favorite != "none" else None,
        internal_statistics_disclaimer=(
            "Преимущество основано на внутренней статистике CS2Eye. "
            "Форма на текущем турнире рассматривается отдельно от общей статистики."
        ),
    )


def _evidence(identifier, *, tournament="Test Cup", opponent="Falcons", opponent_rank=5,
              result="win", series_score="2-1", perf=.2, date="2026-08-20"):
    return FormEvidence(
        evidence_id=identifier, date=date, tournament=tournament, opponent=opponent,
        opponent_rank=opponent_rank, result=result, series_score=series_score,
        performance_vs_expectation=perf,
    )


def _form_team(side, *, form_level="good", reliability=.7, matches=3, score=60.0,
               perf=1.0, evidence=(), previous=None, fallback="none"):
    return TournamentFormTeam(
        team_name=_name(side), form_level=form_level, reliability=reliability,
        matches=matches, score=score, performance_vs_expectation=perf,
        evidence=list(evidence), previous_tournament=previous, fallback=fallback,
    )


def _form(*, state="current_tournament", team_a=None, team_b=None, favored="team_b",
          strength="small", notes=()):
    return TournamentFormSection(
        state=state, team_a=team_a or _form_team("team_a"),
        team_b=team_b or _form_team("team_b", form_level="strong", score=72.0),
        comparison=FormComparison(
            favored_team=favored,
            favored_team_name=_name(favored) if favored in {"team_a", "team_b"} else None,
            strength=strength,
        ), context_notes=list(notes),
    )


def _map_profile(side, *, strong=(), weak=()):
    return TeamMapProfile(team_name=_name(side), strong_maps=list(strong), weak_maps=list(weak))


def _map_item(map_name, *, score, reliability=.75, samples=8, classification):
    return MapProfileItem(
        map=map_name, strength_score=score, reliability=reliability,
        sample_maps=samples, classification=classification,
    )


def _map_reason(type_, side, *, strength="moderate", reliability=.75):
    return MapEdgeReason(type=type_, side=side, side_name=_name(side), strength=strength, reliability=reliability)


def _map_edge(map_name, favorite, *, strength="moderate", reasons, relevance=.8):
    return KeyMapEdge(
        map=map_name, favored_team=favorite, favored_team_name=_name(favorite),
        strength=strength, relevance=relevance, reasons=list(reasons),
    )


def _maps(*, status="available", team_a_profile=None, team_b_profile=None, edges=(), notes=()):
    return MapsSection(
        status=status, team_a=team_a_profile or _map_profile("team_a"),
        team_b=team_b_profile or _map_profile("team_b"), key_map_edges=list(edges),
        context_notes=list(notes),
    )


def _teamplay_signal(map_name, category, side, *, strength="moderate", reliability=.75):
    return TeamplaySignal(
        signal_id=f"teamplay:{map_name}:{category}:{side}", category=category, side=side,
        side_name=_name(side), effect="positive", strength=strength, reliability=reliability,
        fact_type=f"strong_{category}", map=map_name, evidence_id=f"map:{map_name}:{category}",
    )


def _teamplay(*, signals=(), notes=()):
    return TeamplaySection(signals=list(signals), context_notes=list(notes))


def _manual_note(identifier, side, *, polarity="negative", players=(), coach=None,
                 map=None, text="Игрок находится в плохой форме по словам аналитика."):
    return FixedManualNote(
        note_id=identifier, team_name=_name(side), polarity=polarity,
        players=list(players), coach=coach, map=map, text=text,
    )


def _manual(*, team_a=(), team_b=()):
    a, b = list(team_a), list(team_b)
    return ManualContextSection(
        team_a=a, team_b=b,
        empty_message=None if (a or b) else "Ручных комментариев по этому матчу нет.",
    )


def _plan(*, favorite="team_b", advantage="small", confidence="medium",
          prob_a=.42, prob_b=.58, form=None, maps=None, teamplay=None, manual=None):
    return MatchExplanationPlanV2(
        expected_winner=_expected_winner(favorite, prob_b if favorite == "team_b" else prob_a),
        conclusion=_conclusion(favorite=favorite, advantage=advantage, confidence=confidence,
                               prob_a=prob_a, prob_b=prob_b),
        form=form or _form(),
        maps=maps or _maps(status="insufficient", notes=[
            "Недостаточно надёжных данных для уверенного сравнения карт.",
        ]),
        teamplay=teamplay or _teamplay(notes=[
            "Надёжных выраженных различий по доступным teamplay/swing показателям не найдено.",
        ]), manual_context=manual or _manual(),
    )


def _case(case_id, name, tags, plan, *, golden=False, must_mention=(), forbidden=()):
    return LLMQualityCase(
        case_id=case_id, name=name, description=name,
        explanation_plan_snapshot=plan,
        expectations=LLMQualityExpectations(
            must_mention=list(must_mention), forbidden_facts=list(forbidden),
            expected_favored_team=plan.conclusion.favored_team,
            expected_confidence=plan.conclusion.confidence,
        ), tags=tags, golden=golden,
    )


def load_dataset_v2() -> LLMQualityDataset:
    cases = [
        _case(
            "clear_favorite", "Явный фаворит без сильных возражений", ["clear_favorite"],
            _plan(
                advantage="clear", confidence="high", prob_a=.28, prob_b=.72,
                maps=_maps(edges=[_map_edge("dust2", "team_b", strength="clear", reasons=[
                    _map_reason("team_strong_on_map", "team_b"),
                ])]),
                teamplay=_teamplay(signals=[_teamplay_signal("dust2", "ct_side", "team_b")]),
            ), golden=True, must_mention=["dust2"],
        ),
        _case(
            "close_match", "Небольшой перевес 55/45", ["close_match"],
            _plan(advantage="small", confidence="medium", prob_a=.45, prob_b=.55,
                  form=_form(strength="small")),
        ),
        _case(
            "near_even", "Почти равный матч", ["close_match"],
            _plan(advantage="none", confidence="low", prob_a=.49, prob_b=.51,
                  form=_form(favored="none", strength="none"),
                  maps=_maps(status="insufficient", notes=[
                      "Недостаточно надёжных данных для уверенного сравнения карт.",
                  ])),
        ),
        _case(
            "favorite_none_no_ml", "ML-прогноз недоступен", ["insufficient_data"],
            _plan(favorite="none", advantage="none", confidence="insufficient",
                  form=_form(favored="none", strength="none"),
                  maps=_maps(status="insufficient", notes=[
                      "Недостаточно надёжных данных для уверенного сравнения карт.",
                  ])),
            golden=True,
        ),
        _case(
            "tournament_just_started", "Турнир только начинается", ["tournament_just_started"],
            _plan(form=_form(
                state="not_started",
                team_a=_form_team("team_a", fallback="previous_tournament", matches=4,
                                  evidence=[], previous=PreviousTournamentFallback(
                                      tournament="Prior Cup", matches=4,
                                      evidence=[_evidence("series:101", tournament="Prior Cup")],
                                  )),
                team_b=_form_team("team_b", fallback="previous_tournament", matches=3,
                                  evidence=[], previous=PreviousTournamentFallback(
                                      tournament="Prior Cup", matches=3,
                                      evidence=[_evidence("series:102", tournament="Prior Cup")],
                                  )),
                notes=["Турнир только начинается, поэтому команды ещё не сформировали турнирную форму."],
            )),
        ),
        _case(
            "mixed_availability_form", "Неодинаковое число матчей на турнире",
            ["mixed_availability_form"],
            _plan(form=_form(
                state="mixed_availability",
                team_a=_form_team("team_a", fallback="recent_60d", matches=0, score=None,
                                  reliability=None, form_level="unknown"),
                team_b=_form_team("team_b", matches=2, evidence=[_evidence("series:103")]),
                notes=["Турнирная форма команд основана на неодинаковом числе матчей и напрямую не сопоставима."],
            )),
        ),
        _case(
            "insufficient_form_data", "Недостаточно данных о форме обеих команд",
            ["insufficient_form_data"],
            _plan(confidence="low", form=_form(
                state="mixed_availability", favored="none", strength="none",
                team_a=_form_team("team_a", fallback="insufficient", matches=0, score=None,
                                  reliability=None, form_level="unknown", perf=None),
                team_b=_form_team("team_b", fallback="insufficient", matches=0, score=None,
                                  reliability=None, form_level="unknown", perf=None),
                notes=["Для одной или обеих команд недостаточно надёжных данных о форме."],
            )),
        ),
        _case(
            "map_advantage_relevant", "Преимущество на релевантной карте", ["map_advantage"],
            _plan(maps=_maps(
                team_b_profile=_map_profile("team_b", strong=[
                    _map_item("dust2", score=68, classification="strong"),
                ]),
                edges=[_map_edge("dust2", "team_b", reasons=[
                    _map_reason("team_strong_on_map", "team_b"),
                    _map_reason("opponent_weak_on_map", "team_a"),
                ])],
            )), must_mention=["dust2"],
        ),
        _case(
            "map_advantage_split", "Противоположные преимущества на разных картах",
            ["map_advantage", "multiple_map_edges"],
            _plan(advantage="none", confidence="low", prob_a=.5, prob_b=.5, favorite="none",
                  maps=_maps(edges=[
                      _map_edge("dust2", "team_b", reasons=[_map_reason("team_strong_on_map", "team_b")]),
                      _map_edge("inferno", "team_a", reasons=[_map_reason("team_strong_on_map", "team_a")]),
                  ])), must_mention=["dust2", "inferno"],
        ),
        _case(
            "weak_map_sample", "Недостаточно надёжных данных по картам", ["weak_map_sample"],
            _plan(maps=_maps(status="insufficient", notes=[
                "Недостаточно надёжных данных для уверенного сравнения карт.",
            ])),
        ),
        _case(
            "teamplay_signals_present", "Заметные различия в командной игре",
            ["teamplay_signals"],
            _plan(teamplay=_teamplay(signals=[
                _teamplay_signal("mirage", "ct_side", "team_b", strength="clear"),
                _teamplay_signal("mirage", "trading", "team_b"),
            ])),
        ),
        _case(
            "teamplay_empty", "Нет надёжных различий в командной игре", ["teamplay_empty"],
            _plan(teamplay=_teamplay(notes=[
                "Надёжных выраженных различий по доступным teamplay/swing показателям не найдено.",
            ])),
        ),
        _case(
            "manual_notes_team_b_positive", "Положительная ручная заметка о фаворите",
            ["manual_context"],
            _plan(manual=_manual(team_b=[_manual_note(
                "note:1", "team_b", polarity="positive",
                text="Аналитик отмечает уверенную игру состава на последних сборах.",
            )])), golden=True,
        ),
        _case(
            "manual_notes_team_a_negative", "Негативная ручная заметка о претенденте",
            ["manual_context"],
            _plan(manual=_manual(team_a=[_manual_note(
                "note:2", "team_a", polarity="negative",
                text="Аналитик отмечает усталость состава после долгой серии выездных турниров.",
            )])),
        ),
        _case(
            "manual_notes_both_teams", "Ручные заметки по обеим командам",
            ["manual_context"],
            _plan(manual=_manual(
                team_a=[_manual_note("note:3", "team_a", polarity="negative")],
                team_b=[_manual_note("note:4", "team_b", polarity="positive",
                                     text="Аналитик отмечает сыгранность состава.")],
            )),
        ),
        _case(
            "weak_data_overall", "Слабое качество данных по всем разделам", ["weak_data"],
            _plan(
                confidence="low",
                form=_form(state="mixed_availability", favored="none", strength="none",
                          team_a=_form_team("team_a", fallback="insufficient", matches=0, score=None,
                                            reliability=None, form_level="unknown", perf=None),
                          team_b=_form_team("team_b", fallback="insufficient", matches=0, score=None,
                                            reliability=None, form_level="unknown", perf=None),
                          notes=["Для одной или обеих команд недостаточно надёжных данных о форме."]),
                maps=_maps(status="insufficient", notes=[
                    "Недостаточно надёжных данных для уверенного сравнения карт.",
                ]),
                teamplay=_teamplay(notes=[
                    "Надёжных выраженных различий по доступным teamplay/swing показателям не найдено.",
                ]),
            ), golden=True,
        ),
        _case(
            "insufficient_data_no_ml", "Недостаточно данных и нет ML-прогноза",
            ["insufficient_data"],
            _plan(
                favorite="none", advantage="none", confidence="insufficient",
                form=_form(state="not_started", favored="none", strength="none", team_a=_form_team(
                    "team_a", fallback="insufficient", matches=0, score=None, reliability=None,
                    form_level="unknown", perf=None,
                ), team_b=_form_team(
                    "team_b", fallback="insufficient", matches=0, score=None, reliability=None,
                    form_level="unknown", perf=None,
                ), notes=["Турнир только начинается, поэтому команды ещё не сформировали турнирную форму."]),
                maps=_maps(status="insufficient", notes=[
                    "Недостаточно надёжных данных для уверенного сравнения карт.",
                ]),
                teamplay=_teamplay(notes=[
                    "Надёжных выраженных различий по доступным teamplay/swing показателям не найдено.",
                ]),
            ), golden=True,
        ),
    ]
    return LLMQualityDataset(cases=cases)


DATASET_V2 = load_dataset_v2()
