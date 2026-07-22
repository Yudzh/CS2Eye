import datetime
import uuid

from sqlalchemy import Text, String, Integer, DateTime, func, ForeignKey, Date, Float
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


# Таблица в которой хранятся данные по каким демкам был запущен парсинг
class DemoParseRun(Base):
    __tablename__ = "demo_parse_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    demo_file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    demo_file_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    tournament_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    match_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    map_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    map_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    team_a_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    team_b_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Название парсера
    parser_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="demoparser2",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="success",
    )

    rounds_count: Mapped[int] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DemoPlayerMapStat(Base):
    __tablename__ = "demo_player_map_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    parse_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "demo_parse_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "players.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    player_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    rounds_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_damage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    average_damage_per_round: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DemoBombRoundStat(Base):
    __tablename__ = "demo_bomb_round_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    parse_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("demo_parse_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    round_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    planter_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    planter_team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    defuser_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    defuser_team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    outcome: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    plant_tick: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    defuse_tick: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    explosion_tick: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DemoRoundStat(Base):
    __tablename__ = "demo_round_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    parse_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("demo_parse_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    round_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    winner_team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    winner_side: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    ct_team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    t_team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )