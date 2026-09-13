import re
from dataclasses import dataclass

from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3


NUMBER_RE = re.compile(r"(?<![\w:])[-+]?\d+(?:[.,]\d+)?\s*%?")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")
KNOWN_MAPS = {"ancient", "anubis", "cache", "cobblestone", "dust2", "inferno", "mirage", "nuke", "overpass", "train", "vertigo"}
BETTING_RE = re.compile(r"ставк|букмек|коэффициент|валу[йе]|банкрол", re.IGNORECASE)
MANUAL_RE = re.compile(r"ручн\w+ (?:комментар|замет)|аналитик", re.IGNORECASE)


@dataclass
class MatchLLMV3ValidationError(RuntimeError):
    errors: tuple[str, ...]
    codes: tuple[str, ...]

    def __str__(self):
        return "; ".join(self.errors)


class MatchLLMAnalysisV3Validator:
    def validate(self, plan: MatchExplanationPlanV2, analysis: MatchLLMAnalysisV3) -> None:
        errors, codes = [], []
        sections = {
            "expected_winner": (
                analysis.expected_winner_text or "", plan.expected_winner or {},
            ),
            "conclusion": (analysis.conclusion_text, plan.conclusion),
            "form": (analysis.form_text, plan.form),
            "maps": (analysis.maps_text, plan.maps),
            "teamplay": (analysis.teamplay_text, plan.teamplay),
            "manual": (analysis.manual_text, plan.manual_context),
        }
        all_numbers = self._numbers(plan.model_dump(mode="json"))
        team_names = self._strings([
            plan.maps.team_a.team_name, plan.maps.team_b.team_name,
        ])
        supplied_maps = {item.map.casefold() for item in plan.maps.key_map_edges}
        for profile in (plan.maps.team_a, plan.maps.team_b):
            supplied_maps.update(item.map.casefold() for item in (*profile.strong_maps, *profile.weak_maps))
        for name, (text, section_plan) in sections.items():
            if not CYRILLIC_RE.search(text):
                errors.append(f"{name} must contain Russian text"); codes.append("wrong_language")
            if BETTING_RE.search(text):
                errors.append(f"{name} contains betting advice"); codes.append("betting_advice")
            section_payload = (
                section_plan.model_dump(mode="json")
                if hasattr(section_plan, "model_dump") else section_plan
            )
            allowed = self._strings(section_payload) | team_names | {"cs2eye", "ml", "lan", "online", "bo1", "bo3", "bo5"}
            unknown_latin = [word for word in LATIN_WORD_RE.findall(text) if word.casefold() not in allowed]
            if unknown_latin:
                errors.append(f"{name} contains unknown entities: {unknown_latin[:3]}"); codes.append("unknown_entity")
            for token in NUMBER_RE.findall(text):
                value = float(token.rstrip("%").strip().replace(",", "."))
                normalized = token.rstrip("%").strip().replace(",", ".")
                decimals = len(normalized.rsplit(".", 1)[1]) if "." in normalized else 0
                tolerance = .5 * 10 ** -decimals + 1e-9
                if not any(abs(value - allowed_number) <= tolerance for allowed_number in all_numbers):
                    errors.append(f"{name} contains new number: {token}"); codes.append("new_number")
        mentioned_maps = {
            map_name for map_name in KNOWN_MAPS
            if re.search(rf"(?<!\w){re.escape(map_name)}(?!\w)", analysis.maps_text, re.IGNORECASE)
        }
        unknown_maps = mentioned_maps - supplied_maps
        if unknown_maps:
            errors.append(f"maps contains unknown maps: {sorted(unknown_maps)}"); codes.append("unknown_map")
        misplaced = [map_name for map_name in supplied_maps if re.search(rf"(?<!\w){re.escape(map_name)}(?!\w)", analysis.form_text, re.IGNORECASE)]
        if misplaced:
            errors.append(f"form contains map facts: {sorted(misplaced)}"); codes.append("cross_section_fact")
        if (plan.manual_context.team_a or plan.manual_context.team_b) and not MANUAL_RE.search(analysis.manual_text):
            errors.append("manual notes are not labeled as analyst comments"); codes.append("manual_context_unlabeled")
        expected = plan.expected_winner
        expected_text = analysis.expected_winner_text or ""
        if expected is None:
            if not re.search(r"расч[её]т\w* победител\w* недоступ", expected_text, re.IGNORECASE):
                errors.append("expected winner must be explicitly unavailable"); codes.append("expected_winner_unavailable_mismatch")
            if re.search(r"долж\w* выигр\w*|победител\w*\s*[-—:]", expected_text, re.IGNORECASE):
                errors.append("expected winner was invented without ML prediction"); codes.append("expected_winner_changed")
        else:
            if not re.search(re.escape(expected.team_name), expected_text, re.IGNORECASE):
                errors.append("expected winner team differs from ML prediction"); codes.append("expected_winner_changed")
            expected_percent = expected.win_probability * 100
            values = [
                float(token.rstrip("%").strip().replace(",", "."))
                for token in NUMBER_RE.findall(expected_text)
            ]
            if not any(abs(value - expected_percent) <= .51 for value in values):
                errors.append("expected winner probability differs from ML prediction"); codes.append("expected_winner_probability_changed")
            opponent = (
                plan.conclusion.team_b_name
                if expected.team_name == plan.conclusion.team_a_name
                else plan.conclusion.team_a_name
            )
            if re.search(
                rf"(?:долж\w* выигр\w*|победител\w*).{{0,40}}{re.escape(opponent)}|"
                rf"{re.escape(opponent)}.{{0,40}}(?:долж\w* выигр\w*|победител\w*)",
                expected_text, re.IGNORECASE,
            ):
                errors.append("expected winner was reversed"); codes.append("expected_winner_changed")
        favorite = plan.conclusion.favored_team
        if favorite in {"team_a", "team_b"}:
            opponent = plan.conclusion.team_b_name if favorite == "team_a" else plan.conclusion.team_a_name
            escaped = re.escape(opponent)
            if (
                re.search(rf"{escaped}.{{0,50}}(?:фаворит|преимуществ)", analysis.conclusion_text, re.IGNORECASE)
                or re.search(rf"(?:фаворит|преимуществ).{{0,50}}{escaped}", analysis.conclusion_text, re.IGNORECASE)
                or any(
                    re.search(r"(?:ml|модел|вероятност)", sentence, re.IGNORECASE)
                    and re.search(escaped, sentence, re.IGNORECASE)
                    and re.search(r"(?:побед|вероятност|прогноз)", sentence, re.IGNORECASE)
                    for sentence in re.split(r"[.!?]", analysis.conclusion_text)
                )
            ):
                errors.append("conclusion reverses deterministic favorite"); codes.append("conclusion_reversed")
        for edge in plan.maps.key_map_edges:
            opponent_side = "team_b" if edge.favored_team == "team_a" else "team_a"
            opponent = plan.maps.team_b.team_name if opponent_side == "team_b" else plan.maps.team_a.team_name
            # Bound a claim by the next map mention, not by punctuation. LLMs can
            # list opposite edges in one sentence (often separated only by a
            # comma), which must not associate the next map's team with this map.
            map_pattern = "|".join(
                re.escape(item) for item in sorted(supplied_maps, key=len, reverse=True)
            )
            claims = re.split(
                rf"(?=(?<!\w)(?:{map_pattern})(?!\w))",
                analysis.maps_text, flags=re.IGNORECASE,
            )
            for sentence in claims:
                if (
                    re.search(rf"(?<!\w){re.escape(edge.map)}(?!\w)", sentence, re.IGNORECASE)
                    and re.search(re.escape(opponent), sentence, re.IGNORECASE)
                    and re.search(r"(?:имеет|получает|сторон\w+)\s+(?:\w+\s+)?преимуществ|преимущество\s+(?:у|за)\s*", sentence, re.IGNORECASE)
                ):
                    errors.append(f"maps reverses edge for {edge.map}"); codes.append("map_edge_reversed")
        if errors:
            raise MatchLLMV3ValidationError(tuple(errors), tuple(dict.fromkeys(codes)))

    @classmethod
    def _strings(cls, value):
        result = set()
        def walk(item):
            if isinstance(item, str): result.update(word.casefold() for word in LATIN_WORD_RE.findall(item))
            elif isinstance(item, dict):
                for child in item.values(): walk(child)
            elif isinstance(item, list):
                for child in item: walk(child)
        walk(value); return result

    @classmethod
    def _numbers(cls, value):
        result = set()
        def walk(item):
            if isinstance(item, bool) or item is None: return
            if isinstance(item, (int, float)):
                result.add(float(item))
                if 0 <= item <= 1: result.add(float(item) * 100)
            elif isinstance(item, str) and " " in item:
                for token in NUMBER_RE.findall(item): result.add(float(token.rstrip("%").strip().replace(",", ".")))
            elif isinstance(item, dict):
                for child in item.values(): walk(child)
            elif isinstance(item, list):
                for child in item: walk(child)
        walk(value); return result
