import uuid
from datetime import datetime

from sqlalchemy import Text, String, Integer, DateTime, func, ForeignKey, Float
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

    # Путь к файлу
    demo_file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False
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

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class DemoPlayerDamageStat(Base):
    __tablename__ = "demo_player_damage_stats"

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

    player_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    total_damage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    rounds_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    average_damage_per_round: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )