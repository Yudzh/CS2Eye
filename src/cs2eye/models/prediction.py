from datetime import date,datetime
from decimal import Decimal

from sqlalchemy import JSON,Boolean,CheckConstraint,Date,DateTime,ForeignKey,Index,Integer,Numeric,String,UniqueConstraint,func,text
from sqlalchemy.orm import Mapped,mapped_column
from cs2eye.db.base import Base

class WinProbabilityModelArtifact(Base):
    __tablename__="win_probability_model_artifacts"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    model_version:Mapped[str]=mapped_column(String(32),nullable=False)
    feature_schema_version:Mapped[str]=mapped_column(String(32),nullable=False)
    trained_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    training_series:Mapped[int]=mapped_column(Integer,nullable=False);validation_series:Mapped[int]=mapped_column(Integer,nullable=False);test_series:Mapped[int]=mapped_column(Integer,nullable=False)
    artifact:Mapped[dict]=mapped_column(JSON,nullable=False);metrics:Mapped[dict]=mapped_column(JSON,nullable=False);dataset_report:Mapped[dict]=mapped_column(JSON,nullable=False)
    trained:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True,server_default="true")
    quality_gate_passed:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default="false")
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default="false")
    forced_active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default="false")
    __table_args__=(Index("uq_win_probability_one_active", "active", unique=True,
        postgresql_where=text("active = true"), sqlite_where=text("active = 1")),)


class MLFeatureDiagnosticRun(Base):
    __tablename__="ml_feature_diagnostic_runs"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    model_version:Mapped[str]=mapped_column(String(32),nullable=False)
    feature_schema_version:Mapped[str]=mapped_column(String(32),nullable=False)
    sample_size:Mapped[int]=mapped_column(Integer,nullable=False)
    report_json:Mapped[dict]=mapped_column(JSON,nullable=False)

class MatchPrediction(Base):
    __tablename__="match_predictions"
    __table_args__=(UniqueConstraint("series_id","mode","model_version","as_of",name="uq_match_prediction_snapshot"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True);series_id:Mapped[int|None]=mapped_column(ForeignKey("matches.id",ondelete="SET NULL"),index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now());as_of:Mapped[date]=mapped_column(Date,nullable=False)
    mode:Mapped[str]=mapped_column(String(20),nullable=False);source:Mapped[str]=mapped_column(String(24),nullable=False)
    model_version:Mapped[str]=mapped_column(String(32),nullable=False);feature_schema_version:Mapped[str]=mapped_column(String(32),nullable=False)
    team_a_id:Mapped[int]=mapped_column(ForeignKey("teams.id"),nullable=False);team_b_id:Mapped[int]=mapped_column(ForeignKey("teams.id"),nullable=False)
    team_a_probability:Mapped[Decimal]=mapped_column(Numeric(10,8),nullable=False);team_b_probability:Mapped[Decimal]=mapped_column(Numeric(10,8),nullable=False);confidence:Mapped[Decimal]=mapped_column(Numeric(8,6),nullable=False)
    feature_snapshot:Mapped[dict]=mapped_column(JSON,nullable=False);prediction_status:Mapped[str]=mapped_column(String(24),nullable=False)


class PredictionHistorySnapshot(Base):
    __tablename__ = "prediction_history_snapshots"
    __table_args__ = (CheckConstraint("source IN ('pre_match','retrospective')", name="ck_prediction_history_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id", ondelete="SET NULL"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="pre_match", server_default="pre_match")
    team_strength_model_version: Mapped[str | None] = mapped_column(String(64))
    matchup_model_version: Mapped[str | None] = mapped_column(String(64))
    ml_model_version: Mapped[str | None] = mapped_column(String(64))
    ml_feature_schema_version: Mapped[str | None] = mapped_column(String(64))
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    team_strength_a: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    team_strength_b: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    team_strength_winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    matchup_a: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    matchup_b: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    matchup_winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    matchup_factors: Mapped[dict | None] = mapped_column(JSON)
    ml_a_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    ml_b_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    ml_winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    actual_winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))


class TournamentPredictionRun(Base):
    __tablename__ = "tournament_prediction_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    model_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    outdated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    model_status: Mapped[str | None] = mapped_column(String(24))
    quality_gate_passed: Mapped[bool | None] = mapped_column(Boolean)


class TournamentMatchPrediction(Base):
    __tablename__ = "tournament_match_predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_run_id: Mapped[int] = mapped_column(ForeignKey("tournament_prediction_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    source_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"), index=True)
    round_number: Mapped[int | None] = mapped_column(Integer)
    round_label: Mapped[str | None] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    bracket_section: Mapped[str | None] = mapped_column(String(16))
    bracket_position: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    team_a_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    team_b_probability: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    team_a_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    team_b_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    predicted_winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    reliability: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    prediction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    prediction_basis: Mapped[str] = mapped_column(String(24), nullable=False, default="win_probability", server_default="win_probability")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
