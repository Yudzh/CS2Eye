from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func,
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


class DemoPlayerStat(Base):
    __tablename__ = "demo_player_stats"
    __table_args__ = (
        UniqueConstraint("demo_file_id", "steam_id", name="uq_demo_player_steam"),
        UniqueConstraint("demo_file_id", "identity_key", name="uq_demo_player_identity"),
        UniqueConstraint("demo_file_id", "player_id", name="uq_demo_player_linked_player"),
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
