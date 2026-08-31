import re
from dataclasses import dataclass

from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2


NUMBER_RE = re.compile(r"(?<![\w:])[-+]?\d+(?:[.,]\d+)?\s*%?")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")
PLAN_LATIN_TOKEN_RE = re.compile(r"[A-Za-z]{3,}")
MANUAL_RE = re.compile(r"аналитик|ручн\w+ замет", re.IGNORECASE)
ALLOWED_PRODUCT_WORDS = {"cs2eye", "lan", "online"}


@dataclass
class MatchLLMV2ValidationError(RuntimeError):
    errors: tuple[str, ...]
    codes: tuple[str, ...]

    def __str__(self):
        return "; ".join(self.errors)


class MatchLLMAnalysisV2Validator:
    def validate(self, plan: MatchExplanationPlan, analysis: MatchLLMAnalysisV2) -> None:
        errors, codes = [], []
        groups = (
            ("advantage_texts", plan.advantages),
            ("counter_argument_texts", plan.counter_arguments),
            ("contradiction_texts", plan.contradictions),
            ("risk_texts", plan.risks),
            ("limitation_texts", plan.limitations),
        )
        all_text = [analysis.summary]
        allowed_strings = self._strings(plan.model_dump(mode="json"))
        allowed_numbers = self._numbers(plan.model_dump(mode="json"))
        for field, items in groups:
            texts = getattr(analysis, field)
            identifiers = {self._identifier(item) for item in items}
            unknown = set(texts) - identifiers
            if unknown:
                errors.append(f"{field} contains unknown IDs: {sorted(unknown)}")
                codes.append("unknown_text_id")
            required = {
                self._identifier(item) for item in items
                if getattr(item, "importance", None) == "high"
                or getattr(item, "severity", None) == "high"
            }
            missing = required - set(texts)
            if missing:
                errors.append(f"{field} misses required IDs: {sorted(missing)}")
                codes.append("missing_required_text")
            all_text.extend(texts.values())
            for item in items:
                identifier = self._identifier(item)
                if getattr(item, "source_kind", None) == "manual" and identifier in texts:
                    if not MANUAL_RE.search(texts[identifier]):
                        errors.append(f"manual signal {identifier} is not labeled as analyst context")
                        codes.append("manual_context_unlabeled")
        for text in all_text:
            if not CYRILLIC_RE.search(text):
                errors.append("human-readable text must be Russian")
                codes.append("wrong_language")
            # Allow proper names/keys supplied by the plan, reject free English prose.
            unknown_latin = [word for word in LATIN_WORD_RE.findall(text)
                             if word.casefold() not in allowed_strings
                             and word.casefold() not in ALLOWED_PRODUCT_WORDS]
            if unknown_latin:
                errors.append(f"English prose is not allowed: {unknown_latin[:3]}")
                codes.append("wrong_language")
            for token in NUMBER_RE.findall(text):
                value = float(token.rstrip("%").strip().replace(",", "."))
                normalized = token.rstrip("%").strip().replace(",", ".")
                decimals = len(normalized.rsplit(".", 1)[1]) if "." in normalized else 0
                rounding_tolerance = .5 * (10 ** -decimals) + 1e-9
                if not any(
                    abs(value - allowed) <= rounding_tolerance
                    for allowed in allowed_numbers
                ):
                    errors.append(f"new number is not allowed: {token}")
                    codes.append("new_number")
        favorite = plan.conclusion.favored_team
        if favorite in {"team_a", "team_b"}:
            opposite = "team_b" if favorite == "team_a" else "team_a"
            opposite_name = getattr(plan.supporting_context, f"{opposite}_name")
            escaped = re.escape(opposite_name or "")
            reversed_conclusion = bool(opposite_name) and bool(
                re.search(
                    rf"(?<!\w){escaped}(?!\w)\s*(?:[-—:]|является|оста[её]тся|считается|имеет)?\s*"
                    r"(?:явн\w+\s+|небольш\w+\s+|главн\w+\s+)?(?:фаворит|преимуществ)",
                    analysis.summary, re.IGNORECASE,
                )
                or re.search(
                    rf"(?:преимущество|перевес)\s+(?:оста[её]тся\s+)?за\s+{escaped}(?!\w)",
                    analysis.summary, re.IGNORECASE,
                )
            )
            if reversed_conclusion:
                errors.append("summary reverses deterministic conclusion")
                codes.append("conclusion_reversed")
        if errors:
            raise MatchLLMV2ValidationError(tuple(errors), tuple(dict.fromkeys(codes)))

    @staticmethod
    def _identifier(item):
        for name in ("signal_id", "contradiction_id", "risk_id", "limitation_id"):
            if hasattr(item, name):
                return getattr(item, name)
        raise TypeError("plan item has no identifier")

    @classmethod
    def _strings(cls, value):
        result = set()
        def walk(item):
            if isinstance(item, str):
                # Plan keys use snake_case (for example ``force_buy``), while the
                # wording model naturally renders the same supplied term with a
                # space. Underscores are word characters, so LATIN_WORD_RE cannot
                # discover the individual allowed tokens in a snake_case value.
                result.update(
                    word.casefold() for word in PLAN_LATIN_TOKEN_RE.findall(item)
                )
            elif isinstance(item, dict):
                for child in item.values(): walk(child)
            elif isinstance(item, list):
                for child in item: walk(child)
        walk(value)
        return result

    @classmethod
    def _numbers(cls, value):
        result = set()
        def walk(item):
            if isinstance(item, bool) or item is None: return
            if isinstance(item, (int, float)):
                result.add(float(item))
                if 0 <= item <= 1: result.add(float(item) * 100)
            elif isinstance(item, str) and " " in item:
                # Human-readable supplied names may legitimately contain a year or
                # another number (for example a tournament or team name). Technical
                # IDs and enum values contain no spaces and stay excluded.
                for token in NUMBER_RE.findall(item):
                    result.add(float(token.rstrip("%").strip().replace(",", ".")))
            elif isinstance(item, dict):
                for child in item.values(): walk(child)
            elif isinstance(item, list):
                for child in item: walk(child)
        walk(value)
        return result
