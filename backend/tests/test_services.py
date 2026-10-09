from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.repositories.metadata import MetadataRepository
from backend.app.schemas.api import ProviderConfig, SavedQueryCreate
from backend.app.services.analytics.charts import deterministic_summary, recommend_chart
from backend.app.services.database.executor import QueryExecutionError, QueryExecutor
from backend.app.services.database.manager import DatabaseManager
from backend.app.services.llm.factory import create_provider, validate_custom_url
from backend.app.services.llm.providers import GeminiProvider, OpenAICompatibleProvider
from backend.app.services.sql.generator import CorrectionBudget


def services(tmp_path: Path, demo_path: Path):
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path,
        demo_db_path=demo_path,
        metadata_db_path=tmp_path / "metadata.db",
    )
    repository = MetadataRepository(str(settings.metadata_db_path))
    manager = DatabaseManager(settings, repository)
    manager.add_demo()
    return settings, repository, manager


def test_schema_introspection_and_read_only_execution(tmp_path, demo_path):
    _, _, manager = services(tmp_path, demo_path)
    schema = manager.schema("demo")
    orders = next(table for table in schema["tables"] if table["name"] == "orders")
    assert any(column["name"] == "order_date" for column in orders["columns"])
    assert orders["foreign_keys"][0]["referred_table"] == "customers"
    result = QueryExecutor(manager, timeout_seconds=2, max_rows=5).execute(
        "demo", "SELECT id, status FROM orders ORDER BY id"
    )
    assert result["row_count"] == 5
    assert result["truncated"]
    with pytest.raises(QueryExecutionError):
        QueryExecutor(manager, timeout_seconds=2, max_rows=5).execute("demo", "DELETE FROM orders")


def test_sqlite_execution_timeout(tmp_path, demo_path):
    _, _, manager = services(tmp_path, demo_path)
    slow_sql = """WITH RECURSIVE counter(value) AS (
        VALUES(0) UNION ALL SELECT value + 1 FROM counter WHERE value < 100000000
    ) SELECT SUM(value) FROM counter"""
    with pytest.raises(QueryExecutionError, match="interrupted"):
        QueryExecutor(manager, timeout_seconds=0.001, max_rows=5).execute("demo", slow_sql)


def test_repository_history_and_saved_queries(tmp_path):
    repository = MetadataRepository(str(tmp_path / "metadata.db"))
    repository.record_history(
        question="Count orders",
        sql="SELECT COUNT(*) FROM orders",
        database_id="demo",
        provider=None,
        model=None,
        status="success",
        execution_time_ms=4.2,
        row_count=1,
    )
    assert repository.history()[0]["question"] == "Count orders"
    saved = repository.create_saved(
        SavedQueryCreate(name="Order count", question="Count", sql="SELECT COUNT(*) FROM orders")
    )
    assert repository.saved()[0]["id"] == saved["id"]
    assert repository.delete_saved(saved["id"])


def test_provider_selection():
    settings = Settings()
    gemini = create_provider(
        ProviderConfig(provider="gemini", model="gemini-test", api_key=SecretStr("x")), settings
    )
    groq = create_provider(
        ProviderConfig(provider="groq", model="test", api_key=SecretStr("x")), settings
    )
    assert isinstance(gemini, GeminiProvider)
    assert isinstance(groq, OpenAICompatibleProvider)


def test_custom_provider_blocks_ssrf():
    with pytest.raises(ValueError, match="blocked"):
        validate_custom_url("http://127.0.0.1:8000")
    assert validate_custom_url("http://127.0.0.1:8000", allow_local=True).startswith("http")


def test_chart_recommendations_and_formatting():
    time_rows = [{"month": "2025-01-01", "revenue": 10.0}, {"month": "2025-02-01", "revenue": 12.0}]
    assert recommend_chart(time_rows)["type"] == "line"
    assert recommend_chart([{"orders": 42}])["type"] == "kpi"
    assert "total 22.00" in deterministic_summary(time_rows)


def test_sql_correction_retry_limit():
    budget = CorrectionBudget(max_attempts=2)
    analysis_id = budget.start()
    assert budget.consume(analysis_id)
    assert budget.consume(analysis_id)
    assert not budget.consume(analysis_id)
    assert not budget.consume("unknown")
