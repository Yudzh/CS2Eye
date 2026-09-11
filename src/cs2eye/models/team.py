from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    current_roster_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_rosters.id", ondelete="SET NULL", use_alter=True),
        index=True,
    )
    team_strength_v3: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    team_strength_v3_reliability: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    team_strength_v3_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    team_strength_v3_model_version: Mapped[str | None] = mapped_column(String(32))
    team_strength_v3_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    mechanical_strength_v3: Mapped[Decimal | None] = mapped_column(Numeric(8,4))
    supporting_strength_v3: Mapped[Decimal | None] = mapped_column(Numeric(8,4))
    player_strength_v3: Mapped[Decimal | None] = mapped_column(Numeric(8,4))
    player_strength_v3_reliability: Mapped[Decimal | None] = mapped_column(Numeric(8,6))
    player_strength_v3_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    player_strength_v3_model_version: Mapped[str | None] = mapped_column(String(32))
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    stats_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    steam_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    internal_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    internal_rating_maps_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_rounds_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_version: Mapped[str | None] = mapped_column(String(16))
    internal_rating_top15: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    internal_rating_top15_maps_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_top15_rounds_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_top16_30: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    internal_rating_top16_30_maps_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_top16_30_rounds_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    internal_rating_updated_at: Mapped[datetime | None] = mapped_column(
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


class AnalystFactorPlayer(Base):
    __tablename__ = "analyst_factor_players"

    analyst_factor_id: Mapped[int] = mapped_column(
        ForeignKey("analyst_factors.id", ondelete="CASCADE"), primary_key=True,
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True, index=True,
    )


class AnalystFactor(Base):
    __tablename__ = "analyst_factors"
    __table_args__ = (
        CheckConstraint("factor_type IN ('positive','negative')", name="ck_analyst_factors_type"),
        CheckConstraint("environment IN ('lan','online','any')", name="ck_analyst_factors_environment"),
        CheckConstraint(
            "category IS NULL OR category IN ('overall','ct_defense','t_attack','tactics','veto','form','communication','roles','individual','teamplay','mental','coach','roster','other')",
            name="ck_analyst_factors_category",
        ),
        Index("ix_analyst_factors_team_active", "team_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    factor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    map_name: Mapped[str | None] = mapped_column(String(32), index=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="any", server_default="any", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    players: Mapped[list[Player]] = relationship(secondary="analyst_factor_players", lazy="selectin")
    coach: Mapped[Player | None] = relationship(foreign_keys=[coach_id], lazy="selectin")


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


class TeamRoster(Base):
    __tablename__ = "team_rosters"
    __table_args__ = (
        UniqueConstraint("team_id", "fingerprint", name="uq_team_roster_fingerprint"),
        Index("ix_team_rosters_team_current", "team_id", "is_current"),
        Index("uq_team_rosters_one_current", "team_id", unique=True,
              postgresql_where=text("is_current"), sqlite_where=text("is_current = 1")),
        CheckConstraint(
            "source IN ('team_import', 'manual', 'demo', 'migration')",
            name="ck_team_rosters_source",
        ),
        CheckConstraint(
            "resolution_status IN ('complete', 'partial', 'needs_review', 'invalid')",
            name="ck_team_rosters_resolution_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    active_from: Mapped[date | None] = mapped_column(Date)
    active_to: Mapped[date | None] = mapped_column(Date)
    active_from_source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", server_default="unknown",
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class TeamRosterMember(Base):
    __tablename__ = "team_roster_members"
    __table_args__ = (
        UniqueConstraint("roster_id", "player_id", name="uq_team_roster_member_player"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roster_id: Mapped[int] = mapped_column(
        ForeignKey("team_rosters.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), index=True,
    )
    player_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    player_external_id: Mapped[str | None] = mapped_column(String(64))
    role_snapshot: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
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
            "team_id",
            "ranking_date",
            "source",
            name="uq_ranking_snapshot_team_date_source",
        ),
        Index(
            "ix_team_ranking_snapshots_team_date",
            "team_id",
            "ranking_date",
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
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="bo3", server_default="bo3",
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


class TeamStrengthV3Snapshot(Base):
    __tablename__ = "team_strength_v3_snapshots"
    __table_args__ = (UniqueConstraint("team_id", "as_of", "model_version",
                                      name="uq_team_strength_v3_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    reliability: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TeamFormV3Snapshot(Base):
    __tablename__ = "team_form_v3_snapshots"
    __table_args__ = (UniqueConstraint("team_id", "as_of", "model_version",
                                      name="uq_team_form_v3_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    tournament_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id", ondelete="SET NULL"), index=True)
    form_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    form_delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    reliability: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    current_tournament_delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    recent_60d_delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MapStrengthV3Snapshot(Base):
    __tablename__="map_strength_v3_snapshots"
    __table_args__=(UniqueConstraint("team_id","map_name","as_of","model_version",name="uq_map_strength_v3_snapshot"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    team_id:Mapped[int]=mapped_column(ForeignKey("teams.id",ondelete="CASCADE"),nullable=False,index=True)
    map_name:Mapped[str]=mapped_column(String(160),nullable=False,index=True)
    as_of:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    map_score:Mapped[Decimal|None]=mapped_column(Numeric(8,4),nullable=True)
    map_delta:Mapped[Decimal|None]=mapped_column(Numeric(8,4),nullable=True)
    ct_score:Mapped[Decimal|None]=mapped_column(Numeric(8,4))
    ct_delta:Mapped[Decimal|None]=mapped_column(Numeric(8,4))
    t_score:Mapped[Decimal|None]=mapped_column(Numeric(8,4))
    t_delta:Mapped[Decimal|None]=mapped_column(Numeric(8,4))
    reliability:Mapped[Decimal]=mapped_column(Numeric(8,4),nullable=False)
    breakdown:Mapped[dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    model_version:Mapped[str]=mapped_column(String(32),nullable=False)
    calculated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
