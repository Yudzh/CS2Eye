import uuid
from datetime import datetime

from sqlalchemy import Text, String, Integer, DateTime, func
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


# Таблица в которой хранятся данные по каким демкам был запущен парсинг
class DemoParseRun(Base):
    __tablename__ = "demo_parse_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4(),
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

    rounds_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=False,
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
