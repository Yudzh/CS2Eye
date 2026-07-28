from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    bo3_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
    )
    bo3_slug: Mapped[str] = mapped_column(
        String(160),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    logo_url: Mapped[str | None] = mapped_column(
        Text,
    )
    country_code: Mapped[str | None] = mapped_column(
        String(8),
    )
    country_name: Mapped[str | None] = mapped_column(
        String(120),
    )
    region: Mapped[str | None] = mapped_column(
        String(24),
    )
    current_rank: Mapped[int | None] = mapped_column(
        Integer,
        index=True,
    )
    current_points: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
    )
    rank_change: Mapped[int | None] = mapped_column(
        Integer,
    )
    ranking_date: Mapped[date | None] = mapped_column(
        Date,
    )
    is_analytics_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    roster_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bo3_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False,
    )
    bo3_slug: Mapped[str] = mapped_column(
        String(160), nullable=False,
    )
    nickname: Mapped[str] = mapped_column(
        String(160), nullable=False,
    )
    first_name: Mapped[str | None] = mapped_column(String(160))
    last_name: Mapped[str | None] = mapped_column(String(160))
    image_url: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(8))
    country_name: Mapped[str | None] = mapped_column(String(120))
    bo3_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    player_strength: Mapped[int | None] = mapped_column(Integer)
    strength_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    stats_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    is_analytics_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TeamParticipantMembership(Base):
    __tablename__ = "team_participant_memberships"
    __table_args__ = (
        Index(
            "uq_active_team_participant",
            "team_id",
            "player_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_type: Mapped[str] = mapped_column(
        String(16), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    role: Mapped[str | None] = mapped_column(String(24))
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )


class RankingImportRun(Base):
    __tablename__ = "ranking_import_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="bo3",
        server_default="bo3",
    )
    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    ranking_date: Mapped[date | None] = mapped_column(
        Date,
    )
    teams_received: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    teams_activated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    teams_deactivated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    player_profiles_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    player_profiles_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
    )
    source_payload: Mapped[dict[str, Any] | None] = (
        mapped_column(JSON)
    )


class TeamRankingSnapshot(Base):
    __tablename__ = "team_ranking_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "import_run_id",
            "team_id",
            name="uq_ranking_snapshot_run_team",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    import_run_id: Mapped[int] = mapped_column(
        ForeignKey(
            "ranking_import_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey(
            "teams.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    ranking_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    points: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )
    rank_change: Mapped[int | None] = mapped_column(
        Integer,
    )
    roster_payload: Mapped[list[dict[str, Any]]] = (
        mapped_column(
            JSON,
            nullable=False,
            default=list,
        )
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
