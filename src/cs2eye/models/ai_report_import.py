from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from cs2eye.db.base import Base


class AIReportImport(Base):
    __tablename__ = "ai_report_imports"
    __table_args__ = (UniqueConstraint("source_origin", "source_run_id", name="uq_ai_report_source"),)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_origin: Mapped[str] = mapped_column(String(36), nullable=False)
    source_run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    report_run_id: Mapped[int] = mapped_column(ForeignKey("match_llm_analysis_runs.id"), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
