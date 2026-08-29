import re
from difflib import SequenceMatcher

from cs2eye.api.schemas.llm_quality import LLMQualityCase, LLMQualityMetrics
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.services.match_llm_analysis_v2_validator import (
    MatchLLMAnalysisV2Validator, MatchLLMV2ValidationError,
)


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?\s*%?")
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
GENERIC_SUMMARY_RE = re.compile(
    r"^(?:небольшое|малое|умеренное|явное)\s+преимущество\s+(?:оста[её]тся\s+)?"
    r"(?:в\s+пользу|за)\s+\S+[.!]?\s*$", re.IGNORECASE,
)


class MatchLLMQualityEvaluator:
    """Transparent, deterministic evaluation. No LLM or external services."""

    SUMMARY_MAX = 180
    ITEM_MAX = 180
    TOTAL_MAX = 1200
    REPETITION_THRESHOLD = .88

    def __init__(self, validator=None):
        self.validator = validator or MatchLLMAnalysisV2Validator()

    def evaluate(self, case: LLMQualityCase, output: MatchLLMAnalysisV2) -> LLMQualityMetrics:
        texts_by_group = {
            "signal": {**output.advantage_texts, **output.counter_argument_texts},
            "contradiction": output.contradiction_texts,
            "risk": output.risk_texts,
            "limitation": output.limitation_texts,
        }
        expected = case.expectations
        required = {
            "signal": expected.must_cover_signal_ids,
            "contradiction": expected.must_cover_contradiction_ids,
            "risk": expected.must_cover_risk_ids,
            "limitation": expected.must_cover_limitation_ids,
        }
        total_required = sum(len(ids) for ids in required.values())
        covered = sum(
            1 for group, ids in required.items() for identifier in ids
            if texts_by_group[group].get(identifier, "").strip()
        )
        coverage = covered / total_required if total_required else 1.0

        failed = []
        try:
            self.validator.validate(case.explanation_plan_snapshot, output)
            grounding = True
        except MatchLLMV2ValidationError as error:
            grounding = False
            failed.extend(f"grounding:{code}" for code in error.codes)

        all_items = [
            text.strip() for group in texts_by_group.values() for text in group.values()
            if text.strip()
        ]
        normalized = [self._normalize(text) for text in all_items]
        duplicate_pairs = 0
        comparisons = 0
        for index, left in enumerate(normalized):
            for right in normalized[index + 1:]:
                comparisons += 1
                if self._similarity(left, right) >= self.REPETITION_THRESHOLD:
                    duplicate_pairs += 1
        summary_normalized = self._normalize(output.summary)
        summary_copies = sum(
            self._similarity(summary_normalized, item) >= self.REPETITION_THRESHOLD
            for item in normalized
        )
        repetition = max(0.0, 1 - (duplicate_pairs + summary_copies) / max(1, comparisons + 1))
        if duplicate_pairs or summary_copies:
            failed.append("repetition")

        generic_count = sum(bool(GENERIC_RE.match(text)) for text in all_items)
        specific_count = sum(self._is_specific(text, case) for text in all_items)
        item_specificity = (max(0.0, (specific_count - generic_count) / len(all_items))
                            if all_items else (1.0 if not total_required else 0.0))
        summary_specificity = 0.0 if GENERIC_SUMMARY_RE.match(output.summary.strip()) else (
            1.0 if self._is_specific(output.summary, case) else .5
        )
        specificity = .8 * item_specificity + .2 * summary_specificity
        if specificity < .6:
            failed.append("specificity")

        total_length = len(output.summary) + sum(map(len, all_items))
        length_penalties = (
            max(0, len(output.summary) - self.SUMMARY_MAX)
            + sum(max(0, len(text) - self.ITEM_MAX) for text in all_items)
            + max(0, total_length - self.TOTAL_MAX)
        )
        conciseness = max(0.0, 1 - length_penalties / 1000)
        if length_penalties:
            failed.append("conciseness")

        readable = [output.summary, *all_items]
        language_pass = all(self._russian(text) for text in readable)
        if not language_pass:
            failed.append("language")
        forbidden = any(FORBIDDEN_RE.search(text) for text in readable) or any(
            fact.casefold() in " ".join(readable).casefold()
            for fact in expected.forbidden_facts
        )
        if forbidden:
            failed.append("forbidden_wording")
        numeric_restatement = any(NUMBER_RE.search(text) for text in readable)
        if numeric_restatement:
            failed.append("numeric_restatement")
        format_pass = bool(output.summary.strip()) and coverage == 1.0 and not numeric_restatement
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
    def _is_specific(text, case):
        if GENERIC_RE.match(text):
            return False
        concrete_terms = {
            "форма", "карта", "состав", "расписание", "matchup", "матчап", "h2h", "вето",
            "данн", "аналитик", "противореч", "риск", "турнир",
        }
        lowered = text.casefold()
        return any(term in lowered for term in concrete_terms)
