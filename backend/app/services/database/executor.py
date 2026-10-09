from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from backend.app.services.database.manager import DatabaseManager


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


class QueryExecutionError(RuntimeError):
    pass


class QueryExecutor:
    def __init__(self, manager: DatabaseManager, timeout_seconds: int, max_rows: int) -> None:
        self.manager = manager
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows

    def execute(self, database_id: str, sql: str) -> dict[str, Any]:
        info = self.manager.info(database_id)
        engine = self.manager.engine(database_id)
        started = time.perf_counter()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    if info.dialect == "postgresql":
                        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                        connection.exec_driver_sql(
                            f"SET LOCAL statement_timeout = {int(self.timeout_seconds * 1000)}"
                        )
                        if info.allowed_schemas:
                            safe_schemas = [
                                engine.dialect.identifier_preparer.quote_schema(item)
                                for item in info.allowed_schemas
                            ]
                            connection.exec_driver_sql(
                                f"SET LOCAL search_path = {', '.join(safe_schemas)}"
                            )
                    elif info.dialect == "sqlite":
                        connection.exec_driver_sql("PRAGMA query_only = ON")
                        raw = connection.connection.driver_connection
                        deadline = time.monotonic() + self.timeout_seconds
                        raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                    result = connection.execute(text(sql))
                    columns = list(result.keys())
                    mappings = result.mappings().fetchmany(self.max_rows + 1)
                    truncated = len(mappings) > self.max_rows
                    rows = [
                        {key: json_value(value) for key, value in dict(row).items()}
                        for row in mappings[: self.max_rows]
                    ]
                finally:
                    if info.dialect == "sqlite":
                        connection.connection.driver_connection.set_progress_handler(None, 0)
                    transaction.rollback()
        except (DBAPIError, SQLAlchemyError) as exc:
            message = str(getattr(exc, "orig", exc)).splitlines()[0][:500]
            raise QueryExecutionError(message) from exc
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "execution_time_ms": elapsed,
        }
