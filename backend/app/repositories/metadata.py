from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from backend.app.models.metadata import Base, DatabaseMetadata, QueryHistory, SavedQuery
from backend.app.schemas.api import SavedQueryCreate


@dataclass
class DashboardStats:
    executed_queries: int
    successful_queries: int
    average_execution_ms: float
    saved_queries: int


class MetadataRepository:
    def __init__(self, path: str) -> None:
        self.engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _row(model: Any) -> dict[str, Any]:
        return {column.name: getattr(model, column.name) for column in model.__table__.columns}

    def record_history(self, **values: Any) -> str:
        history_id = values.pop("id", uuid4().hex)
        with Session(self.engine) as session:
            session.add(QueryHistory(id=history_id, **values))
            session.commit()
        return history_id

    def history(self, limit: int = 100, search: str | None = None) -> list[dict[str, Any]]:
        statement = select(QueryHistory).order_by(QueryHistory.created_at.desc()).limit(limit)
        if search:
            statement = statement.where(QueryHistory.question.ilike(f"%{search}%"))
        with Session(self.engine) as session:
            return [self._row(item) for item in session.scalars(statement)]

    def create_saved(self, payload: SavedQueryCreate) -> dict[str, Any]:
        item = SavedQuery(id=uuid4().hex, **payload.model_dump())
        with Session(self.engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._row(item)

    def saved(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            return [
                self._row(item)
                for item in session.scalars(
                    select(SavedQuery).order_by(SavedQuery.created_at.desc())
                )
            ]

    def delete_saved(self, saved_id: str) -> bool:
        with Session(self.engine) as session:
            result = session.execute(delete(SavedQuery).where(SavedQuery.id == saved_id))
            session.commit()
            return bool(result.rowcount)

    def stats(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(QueryHistory)) or 0
            success = (
                session.scalar(
                    select(func.count())
                    .select_from(QueryHistory)
                    .where(QueryHistory.status == "success")
                )
                or 0
            )
            avg_ms = (
                session.scalar(
                    select(func.avg(QueryHistory.execution_time_ms)).where(
                        QueryHistory.status == "success"
                    )
                )
                or 0.0
            )
            saved = session.scalar(select(func.count()).select_from(SavedQuery)) or 0
        return asdict(DashboardStats(total, success, round(float(avg_ms), 2), saved))

    def upsert_database(self, database_id: str, name: str, dialect: str, is_demo: bool) -> None:
        with Session(self.engine) as session:
            existing = session.get(DatabaseMetadata, database_id)
            if existing:
                existing.name, existing.dialect = name, dialect
            else:
                session.add(
                    DatabaseMetadata(id=database_id, name=name, dialect=dialect, is_demo=is_demo)
                )
            session.commit()

    def remove_database(self, database_id: str) -> None:
        with Session(self.engine) as session:
            session.execute(delete(DatabaseMetadata).where(DatabaseMetadata.id == database_id))
            session.commit()
