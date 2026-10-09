from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from backend.app.core.config import Settings
from backend.app.repositories.metadata import MetadataRepository


@dataclass
class ConnectionInfo:
    id: str
    name: str
    dialect: str
    url: str = field(repr=False)
    allowed_schemas: list[str] = field(default_factory=list)
    is_demo: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dialect": self.dialect,
            "allowed_schemas": self.allowed_schemas,
            "is_demo": self.is_demo,
            "status": "connected",
        }


class DatabaseManager:
    def __init__(self, settings: Settings, repository: MetadataRepository) -> None:
        self.settings = settings
        self.repository = repository
        self._connections: dict[str, ConnectionInfo] = {}
        self._engines: dict[str, Engine] = {}
        self._schema_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = RLock()

    def add_demo(self) -> None:
        path = self.settings.demo_db_path.resolve().as_posix()
        # SQLAlchemy passes the file: URI through to sqlite3, enforcing read-only access.
        url = f"sqlite:///file:{path}?mode=ro&uri=true"
        self._connections["demo"] = ConnectionInfo(
            id="demo", name="QueryMind Demo", dialect="sqlite", url=url, is_demo=True
        )
        self.repository.upsert_database("demo", "QueryMind Demo", "sqlite", True)

    @staticmethod
    def _validate_url(dialect: str, raw_url: str) -> str:
        try:
            url = make_url(raw_url)
        except Exception as exc:
            raise ValueError("The database URL is invalid.") from exc
        backend = url.get_backend_name()
        if dialect == "postgresql" and backend not in {"postgresql", "postgres"}:
            raise ValueError("A PostgreSQL URL is required.")
        if dialect == "sqlite" and backend != "sqlite":
            raise ValueError("A SQLite URL is required.")
        if dialect == "sqlite":
            database = url.database or ""
            if database == ":memory:":
                raise ValueError("In-memory SQLite databases cannot be registered.")
            if "mode=ro" not in raw_url:
                path = Path(unquote(database)).expanduser().resolve()
                if not path.is_file():
                    raise ValueError("SQLite database file does not exist.")
                raw_url = f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true"
        return raw_url

    @classmethod
    def test_url(cls, dialect: str, raw_url: str) -> dict[str, str]:
        safe_url = cls._validate_url(dialect, raw_url)
        engine = create_engine(safe_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ok", "dialect": dialect}
        finally:
            engine.dispose()

    def connect(
        self, name: str, dialect: str, raw_url: str, allowed_schemas: list[str]
    ) -> dict[str, Any]:
        safe_url = self._validate_url(dialect, raw_url)
        self.test_url(dialect, safe_url)
        database_id = uuid4().hex
        info = ConnectionInfo(
            id=database_id,
            name=name,
            dialect=dialect,
            url=safe_url,
            allowed_schemas=allowed_schemas or (["public"] if dialect == "postgresql" else []),
        )
        with self._lock:
            self._connections[database_id] = info
        self.repository.upsert_database(database_id, name, dialect, False)
        return info.public()

    def remove(self, database_id: str) -> bool:
        if database_id == "demo":
            return False
        with self._lock:
            info = self._connections.pop(database_id, None)
            engine = self._engines.pop(database_id, None)
            self._schema_cache.pop(database_id, None)
        if engine:
            engine.dispose()
        if info:
            self.repository.remove_database(database_id)
        return info is not None

    def list(self) -> list[dict[str, Any]]:
        return [item.public() for item in self._connections.values()]

    def info(self, database_id: str) -> ConnectionInfo:
        try:
            return self._connections[database_id]
        except KeyError as exc:
            raise KeyError(
                "Database connection is unavailable or was not restored after restart."
            ) from exc

    def engine(self, database_id: str) -> Engine:
        with self._lock:
            if database_id not in self._engines:
                info = self.info(database_id)
                self._engines[database_id] = create_engine(info.url, pool_pre_ping=True)
            return self._engines[database_id]

    def schema(self, database_id: str, refresh: bool = False) -> dict[str, Any]:
        cached = self._schema_cache.get(database_id)
        if cached and not refresh and time.monotonic() - cached[0] < 300:
            return cached[1]
        info = self.info(database_id)
        inspector = inspect(self.engine(database_id))
        schemas: list[str | None] = (
            [None] if info.dialect == "sqlite" else (info.allowed_schemas or ["public"])
        )
        tables = []
        for schema_name in schemas:
            for table_name in inspector.get_table_names(schema=schema_name):
                if table_name.startswith(("sqlite_", "pg_")):
                    continue
                columns = inspector.get_columns(table_name, schema=schema_name)
                primary = inspector.get_pk_constraint(table_name, schema=schema_name)
                foreign_keys = inspector.get_foreign_keys(table_name, schema=schema_name)
                tables.append(
                    {
                        "name": table_name,
                        "schema": schema_name,
                        "columns": [
                            {
                                "name": column["name"],
                                "type": str(column["type"]),
                                "nullable": bool(column.get("nullable", True)),
                                "primary_key": column["name"]
                                in (primary.get("constrained_columns") or []),
                            }
                            for column in columns
                        ],
                        "foreign_keys": [
                            {
                                "columns": fk.get("constrained_columns", []),
                                "referred_schema": fk.get("referred_schema"),
                                "referred_table": fk.get("referred_table"),
                                "referred_columns": fk.get("referred_columns", []),
                            }
                            for fk in foreign_keys
                        ],
                    }
                )
        result = {"database_id": database_id, "dialect": info.dialect, "tables": tables}
        if info.is_demo:
            result["business_rules"] = [
                "Realized revenue and sales use completed orders only and equal the sum of order_items.quantity multiplied by order_items.unit_price.",
                "Average order value is the average of per-order realized revenue for completed orders.",
                "Order counts include every order status unless the question explicitly limits the status.",
            ]
        self._schema_cache[database_id] = (time.monotonic(), result)
        return result

    def preview(self, database_id: str, table_name: str, limit: int = 10) -> list[dict[str, Any]]:
        schema = self.schema(database_id)
        names = {table["name"] for table in schema["tables"]}
        if table_name not in names:
            raise ValueError("Unknown or unauthorized table.")
        quoted = self.engine(database_id).dialect.identifier_preparer.quote(table_name)
        with self.engine(database_id).connect() as connection:
            rows = connection.execute(
                text(f"SELECT * FROM {quoted} LIMIT :limit"), {"limit": min(limit, 50)}
            )
            return [dict(row) for row in rows.mappings()]
