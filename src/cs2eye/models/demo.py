from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, Index, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class DemoParseRun(Base):
    __tablename__ = "demo_parse_runs"
    __table_args__ = (UniqueConstraint("demo_file_id", name="uq_demo_parse_run_file"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
    )
    demo_file_id: Mapped[int] = mapped_column(
        ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class DemoMapResult(Base):
    __tablename__ = "demo_map_results"
    __table_args__ = (
        UniqueConstraint("demo_file_id", name="uq_demo_map_results_demo_file"),
        CheckConstraint(
            "result_source IN ('demo_parser', 'manual_override', 'mixed', 'unknown')",
            name="ck_demo_map_results_source",
        ),
        CheckConstraint(
            "metadata_status IN ('complete', 'partial', 'invalid', 'needs_review')",
            name="ck_demo_map_results_status",
        ),
        CheckConstraint(
            "round_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')",
            name="ck_demo_map_results_round_data_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
    )
    demo_file_id: Mapped[int] = mapped_column(
        ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False,
    )
    map_name: Mapped[str | None] = mapped_column(String(160))
    team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    team_a_name: Mapped[str | None] = mapped_column(String(160))
    team_a_score: Mapped[int | None] = mapped_column(Integer)
    team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    team_b_name: Mapped[str | None] = mapped_column(String(160))
    team_b_score: Mapped[int | None] = mapped_column(Integer)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    winner_team_name: Mapped[str | None] = mapped_column(String(160))
    rounds_count: Mapped[int | None] = mapped_column(Integer)
    went_to_overtime: Mapped[bool | None] = mapped_column(Boolean)
    result_source: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_status: Mapped[str] = mapped_column(String(24), nullable=False)
    round_data_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_parsed", server_default="not_parsed",
    )
    rounds_parsed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DemoRound(Base):
    __tablename__ = "demo_rounds"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "round_number", name="uq_demo_round_file_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int | None] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    regulation_round_number: Mapped[int | None] = mapped_column(Integer)
    overtime_number: Mapped[int | None] = mapped_column(Integer)
    overtime_round_number: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    half: Mapped[str] = mapped_column(String(32), nullable=False)
    team_a_side: Mapped[str] = mapped_column(String(8), nullable=False)
    team_b_side: Mapped[str] = mapped_column(String(8), nullable=False)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    winner_team_name: Mapped[str | None] = mapped_column(String(160))
    winner_side: Mapped[str] = mapped_column(String(8), nullable=False)
    end_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    team_a_score_before: Mapped[int | None] = mapped_column(Integer)
    team_b_score_before: Mapped[int | None] = mapped_column(Integer)
    team_a_score_after: Mapped[int | None] = mapped_column(Integer)
    team_b_score_after: Mapped[int | None] = mapped_column(Integer)
    started_at_tick: Mapped[int | None] = mapped_column(BigInteger)
    ended_at_tick: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    is_warmup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DemoTeamSideStat(Base):
    __tablename__ = "demo_team_side_stats"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "team_name", name="uq_demo_side_stat_file_team_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    ct_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ct_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ct_rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ct_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    t_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    t_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    t_rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    t_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    first_half_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_half_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_half_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_half_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DemoTeamOpponentContext(Base):
    __tablename__ = "demo_team_opponent_context"
    __table_args__ = (UniqueConstraint("demo_file_id", "team_id", name="uq_demo_opponent_context_file_team"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    opponent_team_name: Mapped[str | None] = mapped_column(String(160))
    opponent_rank: Mapped[int | None] = mapped_column(Integer)
    opponent_rank_group: Mapped[str] = mapped_column(String(24), nullable=False)
    opponent_rank_source: Mapped[str] = mapped_column(String(24), nullable=False)
    opponent_rank_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("team_ranking_snapshots.id", ondelete="SET NULL"))
    opponent_rank_snapshot_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class TeamMapAggregate(Base):
    __tablename__ = "team_map_aggregates"
    __table_args__ = (
        UniqueConstraint("team_id", "map_name", "aggregation_level", "roster_id", "scope_key", name="uq_team_map_aggregate_business_key"),
        CheckConstraint(
            "(aggregation_level = 'organization' AND roster_id IS NULL) OR "
            "(aggregation_level = 'roster' AND roster_id IS NOT NULL)",
            name="ck_team_map_aggregate_level_roster",
        ),
        Index("uq_team_map_aggregate_organization", "team_id", "map_name", "scope_key",
              unique=True, postgresql_where=text("aggregation_level = 'organization'"),
              sqlite_where=text("aggregation_level = 'organization'")),
        Index("uq_team_map_aggregate_roster", "team_id", "roster_id", "map_name", "scope_key",
              unique=True, postgresql_where=text("aggregation_level = 'roster'"),
              sqlite_where=text("aggregation_level = 'roster'")),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    aggregation_level: Mapped[str] = mapped_column(
        String(24), nullable=False, default="organization", server_default="organization",
    )
    roster_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_rosters.id", ondelete="CASCADE"), index=True,
    )
    map_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False)
    window_size: Mapped[int | None] = mapped_column(Integer)
    opponent_rank_group: Mapped[str | None] = mapped_column(String(24))
    maps_played: Mapped[int] = mapped_column(Integer, nullable=False)
    maps_won: Mapped[int] = mapped_column(Integer, nullable=False)
    maps_lost: Mapped[int] = mapped_column(Integer, nullable=False)
    map_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds_won: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False)
    round_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    ct_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    ct_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False)
    ct_rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False)
    ct_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    t_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    t_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False)
    t_rounds_lost: Mapped[int] = mapped_column(Integer, nullable=False)
    t_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    overtime_maps: Mapped[int] = mapped_column(Integer, nullable=False)
    overtime_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    overtime_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False)
    first_match_date: Mapped[date | None] = mapped_column(Date)
    last_match_date: Mapped[date | None] = mapped_column(Date)
    sample_size_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    freshness_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DemoTeamRoster(Base):
    __tablename__ = "demo_team_rosters"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "team_id", name="uq_demo_team_roster_file_team"),
        CheckConstraint(
            "resolution_status IN ('complete', 'partial', 'needs_review', 'invalid', 'requires_demo_reparse')",
            name="ck_demo_team_rosters_resolution_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    roster_id: Mapped[int | None] = mapped_column(ForeignKey("team_rosters.id", ondelete="SET NULL"), index=True)
    team_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    issues: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DemoPlayerStat(Base):
    __tablename__ = "demo_player_stats"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "steam_id", name="uq_demo_player_steam"),
        UniqueConstraint("demo_file_id", "identity_key", name="uq_demo_player_identity"),
        UniqueConstraint("demo_file_id", "player_id", name="uq_demo_player_linked_player"),
        CheckConstraint(
            "opponent_rank_source IN "
            "('historical_snapshot', 'current_fallback', 'unknown')",
            name="ck_demo_player_stats_opponent_rank_source",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
    )
    demo_file_id: Mapped[int] = mapped_column(
        ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False,
    )
    parse_run_id: Mapped[int] = mapped_column(
        ForeignKey("demo_parse_runs.id", ondelete="CASCADE"), nullable=False,
    )
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    steam_id: Mapped[str | None] = mapped_column(String(32))
    identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(160), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(160))
    demo_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True,
    )
    demo_team_name: Mapped[str | None] = mapped_column(String(160))
    opponent_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True,
    )
    opponent_team_name: Mapped[str | None] = mapped_column(String(160))
    opponent_rank: Mapped[int | None] = mapped_column(Integer)
    opponent_rank_group: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", server_default="unknown",
        index=True,
    )
    opponent_rank_source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown", server_default="unknown",
        index=True,
    )
    opponent_rank_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_ranking_snapshots.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    opponent_rank_snapshot_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
    )
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    kills: Mapped[int] = mapped_column(Integer, nullable=False)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, nullable=False)
    total_damage: Mapped[int] = mapped_column(Integer, nullable=False)
    adr: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    kast_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    kast_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    internal_rating: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    internal_rating_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
