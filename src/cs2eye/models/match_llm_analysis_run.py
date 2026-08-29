from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, event, func, inspect
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class MatchLLMAnalysisRun(Base):
    __tablename__ = "match_llm_analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','completed','failed','skipped_insufficient_data')",
            name="ck_match_llm_analysis_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_llm_analysis_runs.id", ondelete="SET NULL"), index=True,
    )
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), index=True,
    )
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    tournament_id: Mapped[int | None] = mapped_column(
        ForeignKey("tournaments.id", ondelete="SET NULL"), index=True,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analysis_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    llm_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    context_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(160))
    context_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation_plan_schema_version: Mapped[str | None] = mapped_column(String(64))
    explanation_plan_snapshot: Mapped[dict | None] = mapped_column(JSON)
    analysis_snapshot: Mapped[dict | None] = mapped_column(JSON)

    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    schema_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    business_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grounding_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repair_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    validation_error_codes: Mapped[list | None] = mapped_column(JSON)
    grounding_error_codes: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


IMMUTABLE_AFTER_COMPLETION = {
    "context_snapshot", "explanation_plan_schema_version", "explanation_plan_snapshot",
    "analysis_snapshot", "prompt_version", "model", "provider", "as_of",
}


@event.listens_for(MatchLLMAnalysisRun, "before_update")
def prevent_completed_snapshot_mutation(mapper, connection, target) -> None:
    state = inspect(target)
    previous_status = state.attrs.status.history.deleted
    was_terminal = bool(previous_status and previous_status[0] in {
        "completed", "skipped_insufficient_data",
    }) or (not previous_status and target.status in {"completed", "skipped_insufficient_data"})
    if was_terminal and any(state.attrs[name].history.has_changes() for name in IMMUTABLE_AFTER_COMPLETION):
        raise ValueError("completed MatchLLMAnalysisRun snapshots are immutable")
