from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


class ProviderConfig(BaseModel):
    provider: Literal["gemini", "groq", "openrouter", "custom", "ollama"]
    model: str
    api_key: SecretStr | None = None
    base_url: str | None = None
    display_name: str | None = None
    temperature: float = Field(0.1, ge=0, le=2)
    max_tokens: int = Field(1000, ge=128, le=8192)


class ProviderTestRequest(ProviderConfig):
    pass


class DatabaseConnectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dialect: Literal["sqlite", "postgresql"]
    database_url: SecretStr
    allowed_schemas: list[str] = Field(default_factory=list)


class DatabaseTestRequest(BaseModel):
    dialect: Literal["sqlite", "postgresql"]
    database_url: SecretStr


class GenerateQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    database_id: str = "demo"
    provider: ProviderConfig | None = None
    conversation: list[dict[str, str]] = Field(default_factory=list)


class StructuredSQL(BaseModel):
    sql: str
    explanation: str
    referenced_tables: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarification_needed: str | None = None
    suggested_chart: Literal[
        "bar", "horizontal_bar", "line", "area", "scatter", "pie", "histogram", "table", "kpi"
    ] = "table"

    @field_validator("sql")
    @classmethod
    def strip_fences(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("```"):
            lines = value.splitlines()
            value = "\n".join(lines[1:-1]).strip()
        return value.rstrip(";")


class ValidateQueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=100_000)
    database_id: str = "demo"


class ValidationResult(BaseModel):
    valid: bool
    normalized_sql: str | None = None
    validation_id: str | None = None
    referenced_tables: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ExecuteQueryRequest(BaseModel):
    validation_id: str
    question: str = Field(default="Manual SQL query", max_length=2000)
    provider: str | None = None
    model: str | None = None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float
    query_id: str
    chart: dict[str, Any]
    summary: str
    followups: list[str] = Field(default_factory=list)


class ExplainQueryRequest(BaseModel):
    question: str
    columns: list[str]
    rows: list[dict[str, Any]]
    provider: ProviderConfig | None = None


class CorrectQueryRequest(BaseModel):
    analysis_id: str = Field(min_length=16, max_length=64)
    question: str = Field(min_length=3, max_length=2000)
    sql: str = Field(min_length=1, max_length=100_000)
    error: str = Field(min_length=1, max_length=1000)
    database_id: str = "demo"
    provider: ProviderConfig


class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    question: str = Field(max_length=2000)
    sql: str = Field(min_length=1, max_length=100_000)
    database_id: str = "demo"
    category: str = Field(default="General", max_length=80)
