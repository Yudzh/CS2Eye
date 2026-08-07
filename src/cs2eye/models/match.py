from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer,
    String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        UniqueConstraint("name", "year", name="uq_tournaments_name_year"),
        CheckConstraint("environment IN ('lan','online','unknown')", name="ck_tournaments_environment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tier: Mapped[str | None] = mapped_column(String(32))
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("format IN ('bo1','bo3','bo5','unknown')", name="ck_matches_format"),
        CheckConstraint(
            "stage IN ('group','swiss','round_of_32','round_of_16','quarterfinal','semifinal','final','unknown')",
            name="ck_matches_stage",
        ),
        CheckConstraint("environment IN ('lan','online','unknown')", name="ck_matches_environment"),
        CheckConstraint("status IN ('scheduled','in_progress','completed','unknown')", name="ck_matches_status"),
        CheckConstraint("resolution_status IN ('resolved','needs_review','unresolved')", name="ck_matches_resolution_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id", ondelete="SET NULL"), index=True)
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", server_default="unknown")
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    is_playoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_elimination: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    team_a_maps_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    team_b_maps_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved", server_default="unresolved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
