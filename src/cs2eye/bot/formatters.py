from datetime import date, datetime
from html import escape
from typing import Any


STAGE_LABELS = {
    "group": "Group",
    "swiss": "Swiss",
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarterfinal": "Quarterfinal",
    "semifinal": "Semifinal",
    "final": "Final",
}
VALUE_LABELS = {
    "low": "Low", "medium": "Medium", "high": "High",
    "available": "Available", "partial": "Partial", "weak": "Weak",
    "insufficient": "Insufficient",
}


def _betting_restriction_lines(payload: dict[str, Any]) -> list[str]:
    restriction = payload.get("betting_restrictions") or {}
    if not restriction.get("restricted"):
        return []
    items = restriction.get("restrictions") or [restriction]
    lines = []
    titles = {
        "navi_no_match_winner_bets": "NAVI RULE",
        "group_stage_no_match_winner_bets": "GROUP STAGE RULE",
    }
    for item in items:
        if lines:
            lines.append("")
        title = titles.get(item.get("rule"), "BETTING RULE")
        message = escape(str(item.get("message") or ""))
        lines.extend([f"⚠️ <b>{title}</b>", "", message, "", "<i>Ручное пользовательское правило.</i>"])
    return lines


def current_tournaments(
    tournaments: list[dict[str, Any]], *, today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or date.today()
    result = []
    for item in tournaments:
        end = _date(item.get("end_date"))
        start = _date(item.get("start_date"))
        if (end is not None and end >= today) or (end is None and start is not None and start >= today):
            result.append(item)
    return sorted(result, key=lambda item: (_date(item.get("start_date")) or date.max, str(item.get("name") or "")))


def future_matches(
    matches: list[dict[str, Any]], *, today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or date.today()
    result = []
    for item in matches:
        team_a, team_b = item.get("team_a") or {}, item.get("team_b") or {}
        match_date = _date(item.get("match_date"))
        if (
            item.get("status") == "scheduled"
            and match_date is not None and match_date >= today
            and team_a.get("id") is not None and team_a.get("name")
            and team_b.get("id") is not None and team_b.get("name")
        ):
            result.append(item)
    return sorted(result, key=lambda item: (_date(item.get("match_date")) or date.max, int(item.get("id", 0))))


def format_match_card(match: dict[str, Any], context: dict[str, Any]) -> str:
    match_context = context.get("match") or {}
    teams = context.get("teams") or {}
    team_a = teams.get("team_a") or match.get("team_a") or {}
    team_b = teams.get("team_b") or match.get("team_b") or {}
    name_a = escape(str(team_a.get("name") or "Team A"))
    name_b = escape(str(team_b.get("name") or "Team B"))
    tournament = match_context.get("tournament") or match.get("tournament") or {}

    lines = [*_betting_restriction_lines(context)]
    if lines:
        lines.append("")
    lines.append(f"<b>{name_a} vs {name_b}</b>")
    if tournament.get("name"):
        lines.extend(["", escape(str(tournament["name"]))])
    details = []
    match_format = match_context.get("format") or match.get("format")
    environment = match_context.get("environment") or match.get("environment")
    if match_format and match_format != "unknown":
        details.append(str(match_format).upper())
    if environment and environment != "unknown":
        details.append(str(environment).upper())
    if details:
        lines.append(" · ".join(details))
    stage = match_context.get("round_label") or STAGE_LABELS.get(
        match_context.get("stage") or match.get("stage")
    )
    if stage:
        lines.append(escape(str(stage)))

    prediction = context.get("prediction") or {}
    lines.extend(["", "<b>ML prediction</b>"])
    probability_a = prediction.get("team_a_probability")
    probability_b = prediction.get("team_b_probability")
    if prediction.get("status") == "available" and probability_a is not None and probability_b is not None:
        lines.extend([f"{name_a} — {probability_a:.0%}", f"{name_b} — {probability_b:.0%}"])
    else:
        lines[-1] = "<b>ML prediction:</b> unavailable"

    matchup = context.get("matchup") or {}
    score_a, score_b = matchup.get("team_a_score"), matchup.get("team_b_score")
    lines.extend(["", "<b>Matchup Score</b>"])
    if score_a is not None and score_b is not None:
        lines.extend([f"{name_a} — {float(score_a):.1f}", f"{name_b} — {float(score_b):.1f}"])
    else:
        lines[-1] = "<b>Matchup Score:</b> unavailable"

    confidence = matchup.get("confidence_level")
    quality = (context.get("data_quality") or {}).get("overall_status")
    lines.extend([
        "",
        f"Confidence: {VALUE_LABELS.get(confidence, 'Unavailable')}",
        f"Data quality: {VALUE_LABELS.get(quality, 'Unavailable')}",
    ])
    return "\n".join(lines)


def format_he_kill_by_map(context: dict[str, Any]) -> str:
    rows = (context.get("secondary_bets") or {}).get("he_kill_by_map") or []
    if not rows:
        return "<b>HE Kill</b>\n\nHE Kill prediction unavailable"
    lines = ["<b>HE Kill</b>", ""]
    for item in rows:
        if not isinstance(item, dict):
            continue
        map_name = escape(str(item.get("map") or "—").title())
        probability = item.get("probability")
        confidence = VALUE_LABELS.get(item.get("confidence"), "Unavailable")
        percentage = f"{float(probability):.0%}" if probability is not None else "—"
        lines.append(f"{map_name} — {percentage} · {confidence}")
    return _compact(lines) if len(lines) > 2 else "<b>HE Kill</b>\n\nHE Kill prediction unavailable"


def format_llm_analysis(payload: dict[str, Any]) -> str:
    rendered = payload.get("rendered_analysis") or {}
    analysis = payload.get("analysis") or {}
    rendered = rendered if isinstance(rendered, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}
    if analysis.get("schema_version") == "match_llm_analysis.v3":
        sections = (
            ("📌", "Итог", "conclusion_text"),
            ("📈", "Форма", "form_text"),
            ("🗺", "Карты", "maps_text"),
            ("🎯", "Тимплей и свинги", "teamplay_text"),
            ("📝", "Ручная аналитика", "manual_text"),
        )
        lines = [*_betting_restriction_lines(payload.get("context") or {})]
        if lines:
            lines.append("")
        lines.append("🤖 <b>AI-анализ</b>")
        plan = payload.get("explanation_plan") or {}
        if isinstance(plan, dict) and "expected_winner" in plan:
            winner = plan.get("expected_winner")
            lines.append("")
            if isinstance(winner, dict) and winner.get("team_name") and winner.get("win_probability") is not None:
                lines.append(
                    "🏆 <b>По расчётам должна выиграть "
                    f"{escape(str(winner['team_name']))} — {float(winner['win_probability']):.0%}</b>"
                )
            else:
                lines.append("🏆 <b>Расчёт победителя недоступен.</b>")
        for icon, title, key in sections:
            body = escape(_truncate(str(analysis.get(key) or "Данные отсутствуют."), 650))
            lines.extend(["", f"{icon} <b>{title}</b>", body])
        return _compact(lines)
    summary = rendered.get("summary") or analysis.get("summary")
    sections = [
        ("Преимущества", _texts(rendered.get("advantages"), analysis, "key_advantages", "advantage_texts")),
        ("Контраргументы", _texts(rendered.get("counter_arguments"), analysis, "counter_arguments", "counter_argument_texts")),
        ("Противоречия", _texts(rendered.get("contradictions"), analysis, "contradictions", "contradiction_texts")),
        ("Риски", _texts(rendered.get("risks"), analysis, "risks", "risk_texts")),
        ("Ограничения", _texts(rendered.get("limitations"), analysis, "data_limitations", "limitation_texts")),
    ]
    lines = [*_betting_restriction_lines(payload.get("context") or {})]
    if lines:
        lines.append("")
    lines.append("<b>AI-анализ</b>")
    if summary:
        lines.extend(["", "<b>Кратко:</b>", escape(_truncate(str(summary), 900))])
    for title, values in sections:
        if values:
            lines.extend(["", f"<b>{title}:</b>"])
            lines.extend(f"• {escape(_truncate(value, 500))}" for value in values[:5])
    if len(lines) == 1:
        status = payload.get("status")
        if status and status != "completed":
            lines.extend(["", f"Анализ недоступен: {escape(str(status))}."])
        else:
            lines.extend(["", "Сохранённый анализ не содержит текста."])
    return _compact(lines)


def format_maps_veto(match: dict[str, Any], context: dict[str, Any]) -> str:
    teams = context.get("teams") or {}
    names = {
        side: escape(str((teams.get(side) or {}).get("name") or side))
        for side in ("team_a", "team_b")
    }
    matchups = {
        str(item.get("map")): item for item in context.get("map_matchups") or []
        if isinstance(item, dict) and item.get("map")
    }
    likely = (context.get("veto") or {}).get("likely_maps") or []
    lines = ["<b>Карты / veto</b>"]
    if likely:
        lines.extend(["", "<b>Вероятные карты:</b>"])
        for index, item in enumerate(likely[:3], 1):
            map_name = str(item.get("map") or "—")
            edges = (matchups.get(map_name) or {}).get("key_edges") or []
            sides = {edge.get("favored_team") for edge in edges if isinstance(edge, dict)}
            advantage = names[next(iter(sides))] if len(sides) == 1 else "близко"
            side_details = []
            for metric, label in (("ct_side", "CT"), ("t_side", "T")):
                edge = next(
                    (item for item in edges if isinstance(item, dict)
                     and item.get("metric") == metric), None,
                )
                if edge and edge.get("favored_team") in names:
                    side_details.append(f"{label}: {names[edge['favored_team']]}")
            suffix = f" · {', '.join(side_details)}" if side_details else ""
            lines.append(f"{index}. {escape(map_name.title())} — {advantage}{suffix}")
    else:
        lines.extend(["", "Вероятные карты пока недоступны."])
    factual = match.get("veto") or []
    if factual:
        lines.extend(["", "<b>Factual veto:</b>"])
        for item in factual[:7]:
            team = escape(str(item.get("team_name") or "Обе команды"))
            lines.append(f"• {team}: {escape(str(item.get('action') or '—'))} {escape(str(item.get('map_name') or '—').title())}")
    elif likely:
        lines.extend(["", "<b>Veto:</b> calculated"])
    if matchups:
        lines.extend(["", "<b>Оценки карт backend:</b>"])
        for side in ("team_a", "team_b"):
            values = []
            for map_name, item in list(matchups.items())[:5]:
                score = (item.get(side) or {}).get("map_strength")
                if score is not None:
                    values.append(f"{escape(map_name.title())} — {float(score):.1f}")
            lines.append(f"{names[side]}: {', '.join(values) if values else 'данных нет'}")
    return _compact(lines)


def format_form(context: dict[str, Any]) -> str:
    teams = context.get("teams") or {}
    lines = ["<b>Форма</b>"]
    available = False
    for side in ("team_a", "team_b"):
        team = teams.get(side) or {}
        form = team.get("form") or {}
        name = escape(str(team.get("name") or side))
        values = [
            ("Турнир", form.get("tournament_form_score"), form.get("tournament_matches")),
            ("Последние 60 дней", form.get("recent_60d_score"), form.get("recent_60d_matches")),
            ("SoS", form.get("strength_of_schedule_score"), None),
            ("Vs expectation", form.get("performance_vs_expectation_score"), None),
        ]
        lines.extend(["", f"<b>{name}</b>"])
        for label, value, matches in values:
            if value is not None:
                available = True
                suffix = f" · матчей: {int(matches)}" if matches is not None else ""
                lines.append(f"{label}: {float(value):.1f}{suffix}")
    return _compact(lines if available else ["<b>Форма</b>", "", "Данных по форме пока нет."])


def format_h2h(context: dict[str, Any]) -> str:
    teams = context.get("teams") or {}
    a = escape(str((teams.get("team_a") or {}).get("name") or "Team A"))
    b = escape(str((teams.get("team_b") or {}).get("name") or "Team B"))
    h2h = context.get("h2h") or {}
    lines = ["<b>H2H организаций</b>", *_h2h_scope(h2h.get("organizations"), a, b), "", "<b>H2H текущими составами</b>"]
    current = h2h.get("current_rosters") or {}
    if current.get("status") in {"no_meetings", "roster_unavailable"} or not current.get("series_played"):
        lines.append("Текущими составами команды не встречались.")
    else:
        lines.extend(_h2h_scope(current, a, b))
    return _compact(lines)


def _h2h_scope(scope: object, team_a: str, team_b: str) -> list[str]:
    if not isinstance(scope, dict) or not scope.get("series_played"):
        return ["Встреч пока нет."]
    return [
        f"Серии: {int(scope['series_played'])} · карты: {int(scope.get('maps_played') or 0)}",
        f"{team_a}: {int(scope.get('team_a_series_won') or 0)} побед в сериях",
        f"{team_b}: {int(scope.get('team_b_series_won') or 0)} побед в сериях",
    ]


def format_rosters(context: dict[str, Any]) -> str:
    teams = context.get("teams") or {}
    lines = ["<b>Составы</b>"]
    available = False
    for side in ("team_a", "team_b"):
        team = teams.get(side) or {}
        roster = team.get("roster") or {}
        players = roster.get("players") or []
        name = escape(str(team.get("name") or side))
        lines.extend(["", f"<b>{name}</b>"])
        for index, player in enumerate(players[:5], 1):
            available = True
            role = str(player.get("role") or "")
            suffix = f" ({escape(role)})" if role else ""
            lines.append(f"{index}. {escape(str(player.get('name') or '—'))}{suffix}")
        igl = next((player.get("name") for player in players if "igl" in str(player.get("role") or "").casefold()), None)
        if igl:
            lines.append(f"IGL: {escape(str(igl))}")
        coach = roster.get("coach") or {}
        if coach.get("name"):
            lines.append(f"Coach: {escape(str(coach['name']))}")
        if roster.get("stability_score") is not None:
            lines.append(f"Roster stability: {float(roster['stability_score']):.1f}")
    return _compact(lines if available else ["<b>Составы</b>", "", "Данные по составам пока недоступны."])


def _compact(lines: list[str]) -> str:
    compact: list[str] = []
    for line in lines:
        candidate = "\n".join([*compact, line])
        if len(candidate) > 3900:
            compact.append("…")
            break
        compact.append(line)
    return "\n".join(compact)


def format_llm_history(history: list[dict[str, Any]]) -> str:
    lines = ["<b>История AI-анализов</b>"]
    if not history:
        return "\n\n".join([lines[0], "Сохранённых версий пока нет."])
    lines.append("")
    for index, item in enumerate(history, 1):
        if not isinstance(item, dict):
            continue
        created = _datetime_label(item.get("created_at"))
        model = str(item.get("model") or item.get("provider") or "—").replace(":", " ")
        prompt = str(item.get("prompt_version") or "—").rsplit(".", 1)[-1]
        status = "" if item.get("status") == "completed" else f" · {item.get('status', 'unknown')}"
        lines.append(
            f"{index}. {escape(created)} · {escape(model)} · {escape(prompt)}{escape(status)}"
        )
    return "\n".join(lines)


def _texts(
    rendered_items: object, analysis: dict[str, Any], legacy_key: str, v2_key: str,
) -> list[str]:
    if isinstance(rendered_items, list):
        return [str(item["text"]) for item in rendered_items
                if isinstance(item, dict) and item.get("text")]
    legacy = analysis.get(legacy_key)
    if isinstance(legacy, list):
        values = []
        for item in legacy:
            if isinstance(item, dict):
                text = item.get("statement") or item.get("description") or item.get("text")
                if text:
                    values.append(str(text))
        return values
    v2 = analysis.get(v2_key)
    if isinstance(v2, dict):
        return [str(value) for value in v2.values() if value]
    return []


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def _datetime_label(value: object) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y %H:%M") if isinstance(value, datetime) else "—"


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None
