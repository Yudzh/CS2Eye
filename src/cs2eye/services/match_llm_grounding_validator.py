"""Deterministic grounding of MatchLLMAnalysis prose against its source context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import EvidenceKind, MatchLLMAnalysis


EvidenceType = Literal[
    "prediction", "match", "matchup", "matchup_factor", "team", "team_strength",
    "team_form", "roster", "leadership", "recent_series", "veto", "map_matchup",
    "map_edge", "h2h", "manual_note", "data_quality", "tournament",
]


@dataclass(frozen=True)
class EvidenceEntry:
    id: str
    type: EvidenceType
    facts: dict[str, Any]


@dataclass(frozen=True)
class GroundingValidationError:
    code: Literal[
        "unknown_evidence", "incompatible_evidence", "missing_evidence",
        "unsupported_number", "unknown_team", "unknown_player", "unknown_map",
        "probability_hallucination", "summary_unsupported_fact",
        "manual_note_misuse",
    ]
    location: str
    value: str | None = None
    evidence_refs: tuple[str, ...] = ()
    message: str = ""

    def repair_message(self) -> str:
        detail = self.message or self.code.replace("_", " ")
        value = f' Value: "{self.value}".' if self.value is not None else ""
        refs = f" Evidence refs: {list(self.evidence_refs)}." if self.evidence_refs else ""
        return f"{self.code} at {self.location}. {detail}{value}{refs}"


@dataclass(frozen=True)
class GroundingValidationResult:
    valid: bool
    errors: tuple[GroundingValidationError, ...] = ()
    evidence_kinds: dict[str, EvidenceKind] = field(default_factory=dict)


NUMBER_RE = re.compile(r"(?<![\w:])[-+]?\d+(?:[.,]\d+)?\s*%?")
PREDICTION_WORDS = re.compile(
    r"\b(probability|chance|odds|вероятност\w*|шанс\w*)\b", re.IGNORECASE,
)
BETTING_WORDS = re.compile(
    r"\b(bet|wager|stake|bookmaker|ставк\w*|коэффициент\w*)\b", re.IGNORECASE,
)

# A finite map vocabulary makes map hallucination detection deterministic even when
# the current context has no map evidence. Historical names are intentional.
CS2_MAPS = {
    "ancient", "anubis", "cache", "cobblestone", "dust", "dust2", "inferno",
    "mirage", "nuke", "overpass", "train", "vertigo",
}

CATEGORY_TYPES: dict[str, set[str]] = {
    "overall_strength": {"team_strength", "team", "matchup", "matchup_factor"},
    "recent_form": {"team_form", "recent_series", "matchup_factor"},
    "tournament_form": {"team_form", "recent_series"},
    "strength_of_schedule": {"team_form", "recent_series", "matchup_factor"},
    "performance_vs_expectation": {"team_form", "recent_series", "matchup_factor"},
    "roster": {"roster", "manual_note"},
    "map_pool": {"veto", "map_matchup", "map_edge"},
    "veto": {"veto", "map_matchup"},
    "ct_side": {"map_edge"},
    "t_side": {"map_edge"},
    "economy": {"map_edge", "matchup_factor"},
    "opening": {"map_edge", "matchup_factor"},
    "trade": {"map_edge", "matchup_factor"},
    "clutch": {"map_edge", "matchup_factor"},
    "postplant": {"map_edge", "matchup_factor"},
    "retake": {"map_edge", "matchup_factor"},
    "leadership": {"leadership", "manual_note"},
    "h2h": {"h2h"},
    "ml_prediction": {"prediction"},
    "manual_context": {"manual_note"},
    "data_quality": {"data_quality"},
}


class MatchLLMGroundingValidator:
    """Reject facts that cannot be traced to the claim's evidence entries."""

    def validate(
        self, context: MatchAnalysisContext, analysis: MatchLLMAnalysis,
    ) -> GroundingValidationResult:
        registry = self.build_evidence_registry(context)
        errors: list[GroundingValidationError] = []
        kinds: dict[str, EvidenceKind] = {}
        referenced_for_summary: set[str] = set()
        grounded_texts: list[str] = []

        for location, identity, category, text, refs in self._items(analysis):
            referenced_for_summary.update(refs)
            grounded_texts.append(text)
            if not refs:
                errors.append(self._error("missing_evidence", location, None, refs))
                continue
            unknown = [ref for ref in refs if ref not in registry]
            for ref in unknown:
                errors.append(self._error("unknown_evidence", location, ref, refs))
            entries = [registry[ref] for ref in refs if ref in registry]
            if category in CATEGORY_TYPES and entries and not any(
                entry.type in CATEGORY_TYPES[category] for entry in entries
            ):
                errors.append(self._error(
                    "incompatible_evidence", location, category, refs,
                    f"Claim category {category} is not supported by evidence types "
                    f"{sorted({entry.type for entry in entries})}.",
                ))
            if entries:
                kind = self._evidence_kind(entries)
                kinds[identity] = kind
                errors.extend(self._validate_text(context, text, location, refs, entries))
                if kind == "manual" and self._manual_note_misuse(text):
                    errors.append(self._error(
                        "manual_note_misuse", location, None, refs,
                        "Manual-note-only evidence must be described as analyst-provided "
                        "context, not verified statistics.",
                    ))

        summary_facts: list[Any] = []
        for source_text in grounded_texts:
            summary_facts.extend(number for _, number, _ in self._extract_numbers(source_text))
            summary_facts.extend(
                entity for entity in (
                    *self._team_names(context), *self._player_names(context), *CS2_MAPS,
                ) if self._mentioned(source_text, entity)
            )
        favorite = analysis.conclusion.favored_team
        if favorite in {"team_a", "team_b"}:
            favorite_name = getattr(context.teams, favorite).name
            if favorite_name:
                summary_facts.append(favorite_name)
        summary_entries = [EvidenceEntry("validated_claims", "match", {"facts": summary_facts})]
        errors.extend(self._validate_text(
            context, analysis.summary, "summary", tuple(sorted(referenced_for_summary)),
            summary_entries, summary=True,
        ))
        if BETTING_WORDS.search(analysis.summary):
            errors.append(self._error(
                "summary_unsupported_fact", "summary", "betting advice", (),
                "Summary must not contain betting advice.",
            ))
        if favorite in {"team_a", "team_b"}:
            opposite = "team_b" if favorite == "team_a" else "team_a"
            opposite_name = getattr(context.teams, opposite).name
            if opposite_name and re.search(
                rf"(?<!\w){re.escape(opposite_name)}(?!\w).{{0,30}}"
                r"(?:favorite|favoured|фаворит)", analysis.summary, re.IGNORECASE,
            ):
                errors.append(self._error(
                    "summary_unsupported_fact", "summary", "opposite favorite", (),
                    "Summary contradicts the immutable ML favorite.",
                ))
        return GroundingValidationResult(not errors, tuple(errors), kinds)

    @staticmethod
    def build_evidence_registry(context: MatchAnalysisContext) -> dict[str, EvidenceEntry]:
        registry: dict[str, EvidenceEntry] = {}

        def add(identifier: str, kind: EvidenceType, facts: Any) -> None:
            if hasattr(facts, "model_dump"):
                facts = facts.model_dump(mode="json")
            registry[identifier] = EvidenceEntry(identifier, kind, facts)

        team_names = {
            "team_a": context.teams.team_a.name,
            "team_b": context.teams.team_b.name,
        }
        add("prediction", "prediction", {
            **team_names, **context.prediction.model_dump(mode="json"),
        })
        add("matchup", "matchup", {
            **team_names, **context.matchup.model_dump(mode="json"),
        })
        add("veto", "veto", context.veto)
        add("h2h:organizations", "h2h", context.h2h.organizations)
        add("h2h:current_rosters", "h2h", context.h2h.current_rosters)
        add("data_quality", "data_quality", context.data_quality)
        add("manual_context", "manual_note", context.manual_context)
        if context.match.id is not None:
            add(f"match:{context.match.id}", "match", context.match)
        if context.match.tournament.id is not None:
            add(f"tournament:{context.match.tournament.id}", "tournament", context.match.tournament)

        for side_name, team in (("team_a", context.teams.team_a), ("team_b", context.teams.team_b)):
            team_facts = {"side": side_name, "id": team.id, "name": team.name, "rank": team.rank}
            if team.id is not None:
                add(f"team:{team.id}", "team", team_facts)
                add(f"team:{team.id}:strength", "team_strength", {
                    **team_facts, **team.team_strength.model_dump(mode="json"),
                })
                add(f"team:{team.id}:form", "team_form", {
                    **team_facts, **team.form.model_dump(mode="json"),
                })
                add(f"team:{team.id}:roster", "roster", {
                    **team_facts, **team.roster.model_dump(mode="json"),
                })
                add(f"team:{team.id}:leadership", "leadership", {
                    **team_facts, **team.leadership.model_dump(mode="json"),
                })
            for factor in team.team_strength.key_factors:
                add(factor.factor_id, "team_strength", {**team_facts, **factor.model_dump(mode="json")})

        for driver in context.prediction.top_model_drivers:
            add(driver.driver_id, "prediction", driver)
        for factor in context.matchup.factors:
            add(factor.factor_id, "matchup_factor", factor)
        for side_name, series_items in (
            ("team_a", context.recent_series_evidence.team_a),
            ("team_b", context.recent_series_evidence.team_b),
        ):
            team = getattr(context.teams, side_name)
            for series in series_items:
                add(series.evidence_id, "recent_series", {
                    "team": team.name, **series.model_dump(mode="json"),
                })
        for likely_map in context.veto.likely_maps:
            add(f"veto:map:{likely_map.map.lower()}", "veto", likely_map)
        for map_context in context.map_matchups:
            add(f"map:{map_context.map}", "map_matchup", map_context)
            for edge in map_context.key_edges:
                add(edge.evidence_id, "map_edge", {
                    "map": map_context.map, **edge.model_dump(mode="json"),
                })
        for side_name, notes in (
            ("team_a", context.manual_context.team_a),
            ("team_b", context.manual_context.team_b),
        ):
            team = getattr(context.teams, side_name)
            for note in notes:
                add(note.note_id, "manual_note", {
                    "team": team.name, **note.model_dump(mode="json"),
                })
        return registry

    def _validate_text(self, context, text, location, refs, entries, *, summary=False):
        errors: list[GroundingValidationError] = []
        allowed_numbers = self._numbers(entries)
        for token, number, is_percent in self._extract_numbers(text):
            tolerance = 0.5 if is_percent else max(0.005, abs(number) * 1e-6)
            if not any(abs(number - allowed) <= tolerance for allowed in allowed_numbers):
                code = "summary_unsupported_fact" if summary else (
                    "probability_hallucination" if is_percent and PREDICTION_WORDS.search(text)
                    else "unsupported_number"
                )
                errors.append(self._error(code, location, token, refs,
                    f'"{token}" is not present in the referenced evidence.'))

        allowed_strings = {value.casefold() for value in self._strings(entries)}
        all_teams = self._team_names(context)
        all_players = self._player_names(context)
        allowed_maps = {m.casefold() for m in self._maps(entries)}
        for team in all_teams:
            if self._mentioned(text, team) and team.casefold() not in allowed_strings:
                errors.append(self._error("unknown_team", location, team, refs))
        # Unknown opponent names in result-like phrases are detected without pretending
        # every capitalized word is an entity.
        for candidate in self._result_entities(text):
            if candidate.casefold() not in allowed_strings:
                errors.append(self._error("unknown_team", location, candidate, refs))
        for player in all_players:
            if self._mentioned(text, player) and player.casefold() not in allowed_strings:
                errors.append(self._error("unknown_player", location, player, refs))
        for candidate in self._explicit_players(text):
            if candidate.casefold() not in allowed_strings:
                errors.append(self._error("unknown_player", location, candidate, refs))
        for map_name in CS2_MAPS:
            if self._mentioned(text, map_name) and map_name not in allowed_maps:
                errors.append(self._error("unknown_map", location, map_name, refs))
        return errors

    @staticmethod
    def _items(analysis):
        for collection in ("key_advantages", "counter_arguments"):
            for index, item in enumerate(getattr(analysis, collection)):
                yield f"{collection}[{index}].statement", item.claim_id, item.category, item.statement, tuple(item.evidence_refs)
        for index, item in enumerate(analysis.contradictions):
            yield f"contradictions[{index}].description", item.contradiction_id, None, item.description, tuple(item.evidence_refs)
        for index, item in enumerate(analysis.risks):
            yield f"risks[{index}].statement", item.risk_id, item.category, item.statement, tuple(item.evidence_refs)
        for index, item in enumerate(analysis.data_limitations):
            yield f"data_limitations[{index}].statement", item.limitation_id, "data_quality", item.statement, tuple(item.evidence_refs)

    @classmethod
    def _numbers(cls, entries):
        result: set[float] = set()
        def walk(value):
            if isinstance(value, bool) or value is None:
                return
            if isinstance(value, (int, float)):
                result.add(float(value))
                if 0 <= value <= 1:
                    result.add(float(value) * 100)
            elif isinstance(value, str):
                if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
                    result.add(float(value.replace(",", ".")))
                elif re.fullmatch(r"\d+-\d+", value):
                    result.update(float(part) for part in value.split("-"))
            elif isinstance(value, dict):
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        for entry in entries: walk(entry.facts)
        return result

    @staticmethod
    def _strings(entries):
        values: set[str] = set()
        def walk(value):
            if isinstance(value, str): values.add(value)
            elif isinstance(value, dict):
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        for entry in entries: walk(entry.facts)
        return values

    @staticmethod
    def _maps(entries):
        maps: set[str] = set()
        for entry in entries:
            if entry.type in {"veto", "map_matchup", "map_edge", "manual_note"}:
                facts = entry.facts
                if isinstance(facts, dict):
                    value = facts.get("map")
                    if isinstance(value, str): maps.add(value)
                    for item in facts.get("likely_maps", []):
                        if isinstance(item, dict) and isinstance(item.get("map"), str): maps.add(item["map"])
        return maps

    @staticmethod
    def _extract_numbers(text):
        for match in NUMBER_RE.finditer(text):
            token = match.group(0).strip()
            yield token, float(token.rstrip("%").strip().replace(",", ".")), token.endswith("%")

    @staticmethod
    def _team_names(context):
        values = {team.name for team in (context.teams.team_a, context.teams.team_b) if team.name}
        for series in (*context.recent_series_evidence.team_a, *context.recent_series_evidence.team_b):
            if series.opponent.name: values.add(series.opponent.name)
        return values

    @staticmethod
    def _player_names(context):
        values = set()
        for team in (context.teams.team_a, context.teams.team_b):
            values.update(player.name for player in team.roster.players)
            if team.roster.coach: values.add(team.roster.coach.name)
        return values

    @staticmethod
    def _mentioned(text, entity):
        return bool(re.search(rf"(?<!\w){re.escape(entity)}(?!\w)", text, re.IGNORECASE))

    @staticmethod
    def _result_entities(text):
        patterns = (
            r"(?:beat|defeated|lost to|against)\s+([A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)*)",
            r"(?:победил[аи]?|обыграл[аи]?|проиграл[аи]?|против)\s+([A-ZА-ЯЁ][\w.-]*(?:\s+[A-ZА-ЯЁ][\w.-]*)*)",
        )
        return {m.group(1).rstrip(".") for pattern in patterns for m in re.finditer(pattern, text)}

    @staticmethod
    def _explicit_players(text):
        patterns = (r"(?:player|coach)\s+([\w.-]+)", r"(?:игрок|тренер)\s+([\w.-]+)")
        return {m.group(1).rstrip(".") for pattern in patterns for m in re.finditer(pattern, text, re.IGNORECASE)}

    @staticmethod
    def _manual_note_misuse(text):
        return bool(re.search(
            r"\b(statistics? (?:prove|confirm)|statistically (?:proven|confirmed)|"
            r"статистик\w* подтвержда\w*|статистически доказ\w*)\b", text, re.IGNORECASE,
        ))

    @staticmethod
    def _evidence_kind(entries) -> EvidenceKind:
        kinds = set()
        for entry in entries:
            if entry.type == "manual_note": kinds.add("manual")
            elif entry.type == "prediction": kinds.add("ml")
            elif entry.type in {"matchup", "matchup_factor", "veto", "map_matchup", "map_edge"}: kinds.add("deterministic")
            elif entry.type == "data_quality": kinds.add("data_quality")
            else: kinds.add("statistical")
        return next(iter(kinds)) if len(kinds) == 1 else "mixed"

    @staticmethod
    def _error(code, location, value, refs, message=""):
        return GroundingValidationError(code, location, value, tuple(refs), message)
