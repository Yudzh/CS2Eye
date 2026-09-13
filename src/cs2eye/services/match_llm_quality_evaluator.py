import re
from difflib import SequenceMatcher

from cs2eye.api.schemas.llm_quality import LLMQualityCase, LLMQualityMetrics
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.services.match_llm_analysis_v3_validator import (
    MatchLLMAnalysisV3Validator, MatchLLMV3ValidationError,
)


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
FORBIDDEN_RE = re.compile(
    r"\b(?:я\s+(?:думаю|считаю)|я\s+бы\s+поставил|ставк\w*|коэффициент\w*|"
    r"value|вероятность\s+по\s+моей\s+оценке)\b", re.IGNORECASE,
)
GENERIC_RE = re.compile(
    r"^(?:у команды есть преимущества|матч будет интересным|есть некоторые риски|"
    r"следует учитывать некоторые факторы|имеются определенные преимущества)[.!]?\s*$",
    re.IGNORECASE,
)

SECTION_FIELDS = (
    "expected_winner_text", "conclusion_text", "form_text", "maps_text",
    "teamplay_text", "manual_text",
)


class MatchLLMQualityEvaluator:
    """Transparent, deterministic evaluation of MatchLLMAnalysis v3 wording.

    Structural grounding (no hallucinated facts, no reversed favorite/edges, no
    unauthorized numbers or entities) is delegated to MatchLLMAnalysisV3Validator
    — the same validator production uses before accepting a generation. This
    evaluator adds the softer, presentation-quality checks that validator does
    not: repetition, specificity, conciseness, language, and case-specific
    coverage of facts the case expects the wording to surface.
    """

    ITEM_MAX = 600
    TOTAL_MAX = 2200
    REPETITION_THRESHOLD = .88

    def __init__(self, validator=None):
        self.validator = validator or MatchLLMAnalysisV3Validator()

    def evaluate(self, case: LLMQualityCase, output: MatchLLMAnalysisV3) -> LLMQualityMetrics:
        expected = case.expectations
        texts = [getattr(output, field) or "" for field in SECTION_FIELDS]
        joined = " ".join(texts).casefold()
        mentioned = sum(1 for fact in expected.must_mention if fact.casefold() in joined)
        coverage = mentioned / len(expected.must_mention) if expected.must_mention else 1.0

        failed = []
        try:
            self.validator.validate(case.explanation_plan_snapshot, output)
            grounding = True
        except MatchLLMV3ValidationError as error:
            grounding = False
            failed.extend(f"grounding:{code}" for code in error.codes)

        non_empty = [text for text in texts if text.strip()]
        normalized = [self._normalize(text) for text in non_empty]
        duplicate_pairs = 0
        comparisons = 0
        for index, left in enumerate(normalized):
            for right in normalized[index + 1:]:
                comparisons += 1
                if self._similarity(left, right) >= self.REPETITION_THRESHOLD:
                    duplicate_pairs += 1
        repetition = max(0.0, 1 - duplicate_pairs / max(1, comparisons))
        if duplicate_pairs:
            failed.append("repetition")

        generic_count = sum(bool(GENERIC_RE.match(text.strip())) for text in non_empty)
        specific_count = sum(self._is_specific(text) for text in non_empty)
        specificity = (max(0.0, (specific_count - generic_count) / len(non_empty))
                      if non_empty else 0.0)
        if specificity < .6:
            failed.append("specificity")

        total_length = sum(map(len, texts))
        length_penalties = (
            sum(max(0, len(text) - self.ITEM_MAX) for text in texts)
            + max(0, total_length - self.TOTAL_MAX)
        )
        conciseness = max(0.0, 1 - length_penalties / 1000)
        if length_penalties:
            failed.append("conciseness")

        language_pass = bool(non_empty) and all(self._russian(text) for text in non_empty)
        if not language_pass:
            failed.append("language")
        forbidden = any(FORBIDDEN_RE.search(text) for text in texts) or any(
            fact.casefold() in joined for fact in expected.forbidden_facts
        )
        if forbidden:
            failed.append("forbidden_wording")
        format_pass = all(text.strip() for text in texts) and coverage == 1.0
        if not format_pass:
            failed.append("format")

        raw = 100 * (
            .30 * coverage + .25 * float(grounding) + .15 * repetition
            + .10 * specificity + .10 * conciseness
            + .05 * float(language_pass) + .05 * float(format_pass)
        )
        passed = grounding and coverage == 1 and language_pass and format_pass and not forbidden
        return LLMQualityMetrics(
            coverage_score=round(coverage, 4), grounding_pass=grounding,
            repetition_score=round(repetition, 4), specificity_score=round(specificity, 4),
            conciseness_score=round(conciseness, 4), language_pass=language_pass,
            format_pass=format_pass, forbidden_wording_pass=not forbidden,
            quality_score=round(raw, 2), passed=passed,
            failed_checks=list(dict.fromkeys(failed)),
        )

    @staticmethod
    def _normalize(text):
        return " ".join(WORD_RE.findall(text.casefold()))

    @staticmethod
    def _similarity(left, right):
        if not left or not right:
            return 0.0
        sequence = SequenceMatcher(None, left, right).ratio()
        a, b = set(left.split()), set(right.split())
        jaccard = len(a & b) / len(a | b) if a | b else 0
        return max(sequence, jaccard)

    @staticmethod
    def _russian(text):
        cyrillic = len(CYRILLIC_RE.findall(text))
        latin = len(LATIN_RE.findall(text))
        return cyrillic >= 3 and cyrillic >= latin

    @staticmethod
    def _is_specific(text):
        if GENERIC_RE.match(text.strip()):
            return False
        concrete_terms = {
            "форма", "карта", "состав", "matchup", "матчап", "данн", "аналитик",
            "турнир", "тимплей", "сторон", "победител",
        }
        lowered = text.casefold()
        return any(term in lowered for term in concrete_terms)
