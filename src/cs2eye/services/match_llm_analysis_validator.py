from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.services.match_llm_analysis_rules import MATCH_LLM_ANALYSIS_LIMITS
from cs2eye.services.match_llm_grounding_validator import MatchLLMGroundingValidator
from cs2eye.services.match_llm_analysis_rules import matchup_favorite


class MatchLLMAnalysisValidationError(ValueError):
    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        self.codes = tuple(self._code(error) for error in errors)
        super().__init__("; ".join(errors))

    def __str__(self) -> str:
        return "; ".join(self.errors)

    @staticmethod
    def _code(error: str) -> str:
        rules = (
            ("context_schema_version", "context_schema_mismatch"),
            ("exceeds limit", "collection_limit_exceeded"),
            ("summary exceeds", "summary_limit_exceeded"),
            ("unknown evidence refs", "unknown_evidence"),
            ("manual analyst note", "manual_evidence_missing"),
            ("favored_team must be", "favorite_mismatch"),
            ("requires favored_team=none", "favorite_mismatch"),
            ("requires analysis_status=insufficient_data", "insufficient_status"),
            ("requires confidence=insufficient", "insufficient_confidence"),
            ("weak data quality", "weak_data_status"),
            ("opposing ML and Matchup", "ml_matchup_contradiction_missing"),
        )
        return next((code for fragment, code in rules if fragment in error), "business_validation_failed")


class MatchLLMAnalysisValidator:
    """Validate architectural invariants that do not require interpreting prose."""

    def validate(
        self,
        context: MatchAnalysisContext,
        analysis: MatchLLMAnalysis,
    ) -> None:
        errors: list[str] = []

        if analysis.context_schema_version != context.schema_version:
            errors.append("analysis context_schema_version does not match the context")

        for collection in (
            "key_advantages", "counter_arguments", "contradictions", "risks",
        ):
            if len(getattr(analysis, collection)) > MATCH_LLM_ANALYSIS_LIMITS[collection]:
                errors.append(
                    f"{collection} exceeds limit "
                    f"{MATCH_LLM_ANALYSIS_LIMITS[collection]}"
                )
        if len(analysis.summary) > MATCH_LLM_ANALYSIS_LIMITS["summary_characters"]:
            errors.append("summary exceeds character limit")

        known_refs, manual_refs = self.evidence_registry(context)
        for owner, refs, category in self._referenced_items(analysis):
            unknown = sorted(set(refs) - known_refs)
            if unknown:
                errors.append(f"{owner} contains unknown evidence refs: {', '.join(unknown)}")
            if category == "manual_context" and not set(refs).intersection(manual_refs):
                errors.append(f"{owner} must reference a manual analyst note")

        prediction = context.prediction
        favored = analysis.conclusion.favored_team
        if context.data_quality.overall_status == "insufficient":
            if favored != "none":
                errors.append("insufficient data quality requires favored_team=none")
        elif prediction.status == "available":
            a = prediction.team_a_probability
            b = prediction.team_b_probability
            expected = "none" if a is None or b is None or a == b else (
                "team_a" if a > b else "team_b"
            )
            if favored != expected:
                errors.append(
                    f"favored_team must be {expected} for the immutable ML prediction"
                )
        elif favored != "none":
            errors.append("favored_team must be none when ML prediction is unavailable")

        if context.data_quality.overall_status == "insufficient":
            if analysis.analysis_status != "insufficient_data":
                errors.append(
                    "insufficient data quality requires analysis_status=insufficient_data"
                )
            if analysis.conclusion.confidence != "insufficient":
                errors.append(
                    "insufficient data quality requires confidence=insufficient"
                )
        elif (
            context.data_quality.overall_status == "weak"
            and analysis.analysis_status != "limited"
        ):
            errors.append("weak data quality requires analysis_status=limited")
        elif analysis.analysis_status == "insufficient_data":
            errors.append(
                "analysis_status=insufficient_data requires insufficient data quality"
            )

        if self._ml_matchup_conflict(context):
            grounded_conflict = any(
                {"prediction", "matchup"}.issubset(item.evidence_refs)
                for item in analysis.contradictions
            )
            if not grounded_conflict:
                errors.append(
                    "opposing ML and Matchup favorites require a contradiction "
                    "referencing prediction and matchup"
                )

        if errors:
            raise MatchLLMAnalysisValidationError(tuple(errors))

    @staticmethod
    def _ml_matchup_conflict(context: MatchAnalysisContext) -> bool:
        prediction = context.prediction
        matchup = context.matchup
        if (
            prediction.status != "available"
            or prediction.team_a_probability is None
            or prediction.team_b_probability is None
            or prediction.team_a_probability == prediction.team_b_probability
            or matchup.team_a_score is None
            or matchup.team_b_score is None
        ):
            return False
        ml_favorite = (
            "team_a"
            if prediction.team_a_probability > prediction.team_b_probability
            else "team_b"
        )
        deterministic_favorite = matchup_favorite(matchup.team_a_score)
        return (
            deterministic_favorite is not None
            and ml_favorite != deterministic_favorite
        )

    @staticmethod
    def evidence_registry(
        context: MatchAnalysisContext,
    ) -> tuple[set[str], set[str]]:
        registry = MatchLLMGroundingValidator.build_evidence_registry(context)
        refs = set(registry)
        manual_refs = {
            identifier for identifier, entry in registry.items()
            if entry.type == "manual_note" and identifier != "manual_context"
        }
        return refs, manual_refs

    @staticmethod
    def _referenced_items(analysis: MatchLLMAnalysis):
        for collection_name in ("key_advantages", "counter_arguments"):
            for claim in getattr(analysis, collection_name):
                yield claim.claim_id, claim.evidence_refs, claim.category
        for contradiction in analysis.contradictions:
            yield contradiction.contradiction_id, contradiction.evidence_refs, None
        for risk in analysis.risks:
            yield risk.risk_id, risk.evidence_refs, risk.category
        for limitation in analysis.data_limitations:
            yield limitation.limitation_id, limitation.evidence_refs, "data_quality"
