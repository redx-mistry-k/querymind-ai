from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str] = mapped_column(Text)
    database_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str] = mapped_column(Text)
    database_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(80), default="General")


class DatabaseMetadata(Base):
    """Non-secret connection metadata. Credentials intentionally live only in memory."""

    __tablename__ = "database_metadata"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    dialect: Mapped[str] = mapped_column(String(20))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
