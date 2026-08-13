from datetime import date,datetime
from decimal import Decimal

from sqlalchemy import JSON,Boolean,Date,DateTime,ForeignKey,Integer,Numeric,String,UniqueConstraint,func
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
    is_active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default="false")

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
