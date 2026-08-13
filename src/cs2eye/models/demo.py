from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text,
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
        CheckConstraint(
            "bomb_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')",
            name="ck_demo_map_results_bomb_data_status",
        ),
        CheckConstraint(
            "economy_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')",
            name="ck_demo_map_results_economy_data_status",
        ),
        CheckConstraint(
            "combat_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')",
            name="ck_demo_map_results_combat_data_status",
        ),
        CheckConstraint(
            "utility_data_status IN ('not_parsed', 'complete', 'partial', 'needs_review', 'invalid')",
            name="ck_demo_map_results_utility_data_status",
        ),
        CheckConstraint(
            "round_swing_status IN ('not_calculated', 'complete', 'partial', 'model_not_trained', 'needs_review', 'invalid')",
            name="ck_demo_map_results_round_swing_status",
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
    bomb_data_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_parsed", server_default="not_parsed",
    )
    economy_data_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_parsed", server_default="not_parsed",
    )
    combat_data_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_parsed", server_default="not_parsed",
    )
    utility_data_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_parsed", server_default="not_parsed",
    )
    round_swing_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_calculated", server_default="not_calculated",
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
    bomb_planted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    bomb_defused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    bomb_exploded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_pistol_round: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    pistol_round_number: Mapped[int | None] = mapped_column(Integer)
    team_a_equipment_value: Mapped[int | None] = mapped_column(Integer)
    team_b_equipment_value: Mapped[int | None] = mapped_column(Integer)
    team_a_economy: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    team_b_economy: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
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


class DemoTeamBombStat(Base):
    __tablename__ = "demo_team_bomb_stats"
    __table_args__ = (UniqueConstraint("demo_file_id", "team_name", name="uq_demo_bomb_stat_file_team_name"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    t_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bomb_plants: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plant_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    postplant_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    postplant_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    postplant_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    postplant_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    retake_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retake_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retake_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retake_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    bomb_explosions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bomb_defuses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DemoTeamEconomyStat(Base):
    __tablename__ = "demo_team_economy_stats"
    __table_args__ = (UniqueConstraint("demo_file_id", "team_name", name="uq_demo_economy_file_team_name"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    pistol_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pistol_rounds_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_pistol_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_pistol_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_pistol_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_pistol_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    both_pistols_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    both_pistols_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pistol_conversion_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pistol_conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    post_pistol_vs_force_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    post_pistol_vs_force_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_round_comeback_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    second_round_comeback_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eco_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eco_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    force_buy_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    force_buy_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    full_buy_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    full_buy_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anti_eco_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anti_eco_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    full_buy_vs_full_buy_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    full_buy_vs_full_buy_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    force_vs_full_buy_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    force_vs_full_buy_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    save_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    players_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    save_data_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_parsed")
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
    bomb_t_rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    bomb_plants: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    plant_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    postplant_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    postplant_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    postplant_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    postplant_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    retake_opportunities: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retake_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retake_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retake_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    bomb_explosions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    bomb_defuses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    economy_data: Mapped[dict | None] = mapped_column(JSON)
    combat_data: Mapped[dict | None] = mapped_column(JSON)
    utility_data: Mapped[dict | None] = mapped_column(JSON)
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
    combat_data: Mapped[dict | None] = mapped_column(JSON)
    utility_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class DemoKill(Base):
    __tablename__ = "demo_kills"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "round_id", "tick", "victim_identity_key", name="uq_demo_kill_event"),
        Index("ix_demo_kills_file_tick", "demo_file_id", "tick"),
        Index("ix_demo_kills_round_tick", "round_id", "tick"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attacker_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    victim_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    assister_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    attacker_identity_key: Mapped[str | None] = mapped_column(String(255))
    victim_identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    assister_identity_key: Mapped[str | None] = mapped_column(String(255))
    attacker_name: Mapped[str | None] = mapped_column(String(160))
    victim_name: Mapped[str] = mapped_column(String(160), nullable=False)
    attacker_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    victim_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    attacker_team_name: Mapped[str | None] = mapped_column(String(160))
    victim_team_name: Mapped[str | None] = mapped_column(String(160))
    attacker_side: Mapped[str | None] = mapped_column(String(8))
    victim_side: Mapped[str | None] = mapped_column(String(8))
    weapon: Mapped[str | None] = mapped_column(String(80))
    is_headshot: Mapped[bool | None] = mapped_column(Boolean)
    is_teamkill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_suicide: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_opening_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_trade_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_traded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DemoDamageEvent(Base):
    __tablename__ = "demo_damage_events"
    __table_args__ = (
        Index("ix_demo_damage_events_round_tick", "round_id", "tick"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attacker_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    victim_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    attacker_identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    victim_identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attacker_side: Mapped[str | None] = mapped_column(String(8))
    victim_side: Mapped[str | None] = mapped_column(String(8))
    health_damage: Mapped[int] = mapped_column(Integer, nullable=False)


class DemoBombEvent(Base):
    __tablename__ = "demo_bomb_events"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "event_kind", "tick", name="uq_demo_bomb_event"),
        Index("ix_demo_bomb_events_round_tick", "round_id", "tick"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    bombsite: Mapped[str | None] = mapped_column(String(8))


class RoundWinModelArtifact(Base):
    __tablename__ = "round_win_model_artifacts"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    feature_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_matches: Mapped[int] = mapped_column(Integer, nullable=False)
    training_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact: Mapped[dict] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalization: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class DemoRoundSwingEvent(Base):
    __tablename__ = "demo_round_swing_events"
    __table_args__ = (
        UniqueConstraint("kill_id", "model_version", name="uq_demo_round_swing_kill_model"),
        Index("ix_demo_round_swing_player", "credited_player_id", "model_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    kill_id: Mapped[int] = mapped_column(ForeignKey("demo_kills.id", ondelete="CASCADE"), nullable=False)
    model_version: Mapped[str] = mapped_column(String(16), nullable=False)
    state_before: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_after: Mapped[dict] = mapped_column(JSON, nullable=False)
    probability_t_before: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    probability_t_after: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    event_swing: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    credited_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    credited_identity_key: Mapped[str | None] = mapped_column(String(255))
    attribution: Mapped[dict] = mapped_column(JSON, nullable=False)
    contexts: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)


class DemoTeamCombatStat(Base):
    __tablename__ = "demo_team_combat_stats"
    __table_args__ = (UniqueConstraint("demo_file_id", "team_name", name="uq_demo_combat_file_team"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    combat_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class DemoUtilityEvent(Base):
    __tablename__ = "demo_utility_events"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "event_kind", "tick", "player_identity_key", "target_identity_key", "grenade_type", name="uq_demo_utility_event"),
        Index("ix_demo_utility_events_file_tick", "demo_file_id", "tick"),
        Index("ix_demo_utility_events_round_tick", "round_id", "tick"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("demo_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    grenade_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    raw_grenade_type: Mapped[str] = mapped_column(String(32), nullable=False)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)
    player_identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    player_name: Mapped[str] = mapped_column(String(160), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str | None] = mapped_column(String(160))
    side: Mapped[str | None] = mapped_column(String(8))
    target_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    target_identity_key: Mapped[str | None] = mapped_column(String(255))
    target_name: Mapped[str | None] = mapped_column(String(160))
    target_relation: Mapped[str | None] = mapped_column(String(12))
    damage: Mapped[int | None] = mapped_column(Integer)
    flash_duration: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class DemoTeamUtilityStat(Base):
    __tablename__ = "demo_team_utility_stats"
    __table_args__ = (UniqueConstraint("demo_file_id", "team_name", name="uq_demo_utility_file_team"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    demo_file_id: Mapped[int] = mapped_column(ForeignKey("demo_files.id", ondelete="CASCADE"), nullable=False, index=True)
    demo_map_result_id: Mapped[int] = mapped_column(ForeignKey("demo_map_results.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    utility_data: Mapped[dict] = mapped_column(JSON, nullable=False)
