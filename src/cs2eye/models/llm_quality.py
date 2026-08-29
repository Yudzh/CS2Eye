from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class LLMQualityRun(Base):
    __tablename__ = "llm_quality_runs"
    __table_args__ = (CheckConstraint("status IN ('completed','failed')",
                                     name="ck_llm_quality_run_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reasoning_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    explanation_plan_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    llm_output_snapshot: Mapped[dict | None] = mapped_column(JSON)
    deterministic_metrics: Mapped[dict | None] = mapped_column(JSON)
    quality_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class LLMQualityReview(Base):
    __tablename__ = "llm_quality_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quality_run_id: Mapped[int] = mapped_column(
        ForeignKey("llm_quality_runs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    language_quality: Mapped[str] = mapped_column(String(16), nullable=False)
    clarity: Mapped[str] = mapped_column(String(16), nullable=False)
    usefulness: Mapped[str] = mapped_column(String(16), nullable=False)
    missing_important_point: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    incorrect_emphasis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    too_verbose: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    too_generic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
