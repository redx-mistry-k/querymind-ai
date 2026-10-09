from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "QueryMind AI"
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    app_host: str = Field(default_factory=lambda: os.getenv("APP_HOST", "127.0.0.1"))
    api_port: int = Field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    streamlit_port: int = Field(default_factory=lambda: int(os.getenv("STREAMLIT_PORT", "8501")))
    backend_url: str = Field(
        default_factory=lambda: os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    )
    api_access_token: str = Field(default_factory=lambda: os.getenv("QUERYMIND_API_TOKEN", ""))
    public_demo_mode: bool = Field(default_factory=lambda: _bool("PUBLIC_DEMO_MODE"))
    public_demo_requests_per_minute: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_REQUESTS_PER_MINUTE", "120"))
    )
    public_demo_llm_calls_per_minute: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_LLM_CALLS_PER_MINUTE", "5"))
    )
    public_demo_llm_calls_per_session: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_LLM_CALLS_PER_SESSION", "20"))
    )
    public_demo_executions_per_minute: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_EXECUTIONS_PER_MINUTE", "20"))
    )
    public_demo_max_query_rows: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_MAX_QUERY_ROWS", "250"))
    )
    public_demo_query_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("PUBLIC_DEMO_QUERY_TIMEOUT_SECONDS", "5"))
    )
    frontend_origins: list[str] = Field(
        default_factory=lambda: [
            item.strip()
            for item in os.getenv(
                "FRONTEND_ORIGINS", "http://127.0.0.1:8501,http://localhost:8501"
            ).split(",")
            if item.strip()
        ]
    )
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openrouter_api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    default_ai_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_AI_PROVIDER", ""))
    default_ai_model: str = Field(default_factory=lambda: os.getenv("DEFAULT_AI_MODEL", ""))
    custom_llm_name: str = Field(
        default_factory=lambda: os.getenv("CUSTOM_LLM_NAME", "Custom Provider")
    )
    custom_llm_base_url: str = Field(default_factory=lambda: os.getenv("CUSTOM_LLM_BASE_URL", ""))
    custom_llm_api_key: str = Field(default_factory=lambda: os.getenv("CUSTOM_LLM_API_KEY", ""))
    custom_llm_model: str = Field(default_factory=lambda: os.getenv("CUSTOM_LLM_MODEL", ""))
    allow_local_custom_llm: bool = Field(default_factory=lambda: _bool("ALLOW_LOCAL_CUSTOM_LLM"))
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    max_query_rows: int = Field(default_factory=lambda: int(os.getenv("MAX_QUERY_ROWS", "1000")))
    query_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("QUERY_TIMEOUT_SECONDS", "15"))
    )
    max_sql_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_SQL_RETRIES", "2")))
    max_conversation_turns: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONVERSATION_TURNS", "6"))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    demo_db_path: Path = ROOT_DIR / "data" / "demo" / "querymind_demo.db"
    metadata_db_path: Path = ROOT_DIR / "data" / "querymind.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
