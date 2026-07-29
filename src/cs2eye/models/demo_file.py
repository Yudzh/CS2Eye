from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from cs2eye.db.base import Base


class DemoFile(Base):
    __tablename__ = "demo_files"
    __table_args__ = (
        UniqueConstraint(
            "tournament_slug", "match_date", "original_filename",
            name="uq_demo_files_tournament_date_filename",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
    )
    tournament_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tournament_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    match_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
