from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import SecretStr

from backend.app.api.dependencies import Services, get_services
from backend.app.schemas.api import (
    CorrectQueryRequest,
    DatabaseConnectRequest,
    DatabaseTestRequest,
    ExecuteQueryRequest,
    ExplainQueryRequest,
    GenerateQueryRequest,
    ProviderConfig,
    ProviderTestRequest,
    QueryResult,
    SavedQueryCreate,
    ValidateQueryRequest,
    ValidationResult,
)
from backend.app.services.analytics.charts import (
    deterministic_summary,
    recommend_chart,
    suggest_followups,
)
from backend.app.services.database.executor import QueryExecutionError
from backend.app.services.llm.base import LLMError
from backend.app.services.llm.factory import create_provider
from backend.app.services.sql.generator import correct_sql, generate_sql

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)
_validation_tickets: dict[str, dict[str, Any]] = {}
TICKET_TTL_SECONDS = 600

EXAMPLE_QUERIES = [
    {
        "question": "Show the top 10 products by revenue.",
        "sql": """SELECT p.name AS product, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi JOIN products p ON p.id = oi.product_id
JOIN orders o ON o.id = oi.order_id WHERE o.status = 'completed'
GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 10""",
    },
    {
        "question": "Show monthly revenue trends.",
        "sql": """SELECT strftime('%Y-%m', o.order_date) AS month,
ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'completed' GROUP BY month ORDER BY month""",
    },
    {
        "question": "Which region generates the highest revenue?",
        "sql": """SELECT r.name AS region, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM regions r JOIN customers c ON c.region_id = r.id JOIN orders o ON o.customer_id = c.id
JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'completed'
GROUP BY r.id, r.name ORDER BY revenue DESC""",
    },
    {
        "question": "What percentage of orders were cancelled?",
        "sql": """SELECT ROUND(100.0 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2)
AS cancelled_percentage FROM orders""",
    },
]


def _public_demo_denied(services: Services, feature: str) -> None:
    if services.settings.public_demo_mode:
        raise HTTPException(
            403,
            detail={
                "code": "public_demo_restriction",
                "message": f"{feature} is disabled in the public demo.",
            },
        )


def _require_demo_database(database_id: str, services: Services) -> None:
    if services.settings.public_demo_mode and database_id != "demo":
        raise HTTPException(
            403,
            detail={
                "code": "public_demo_database",
                "message": "Only the fictional QueryMind demo database is available in public mode.",
            },
        )


def _with_environment_key(config: ProviderConfig, services: Services) -> ProviderConfig:
    if config.api_key and config.api_key.get_secret_value():
        return config
    key = {
        "gemini": services.settings.gemini_api_key,
        "groq": services.settings.groq_api_key,
        "openrouter": services.settings.openrouter_api_key,
        "custom": services.settings.custom_llm_api_key,
    }.get(config.provider, "")
    updates: dict[str, Any] = {"api_key": SecretStr(key)} if key else {}
    if config.provider == "custom":
        updates["base_url"] = config.base_url or services.settings.custom_llm_base_url
    return config.model_copy(update=updates)


def _provider(config: ProviderConfig, services: Services):
    if services.settings.public_demo_mode and config.provider in {"custom", "ollama"}:
        raise HTTPException(
            403,
            detail={
                "code": "public_demo_provider",
                "message": "Custom and local provider endpoints are disabled in the public demo.",
            },
        )
    config = _with_environment_key(config, services)
    if config.provider != "ollama" and not (config.api_key and config.api_key.get_secret_value()):
        raise HTTPException(
            400,
            detail={
                "code": "missing_api_key",
                "message": "Configure an API key for this provider.",
            },
        )
    try:
        return create_provider(config, services.settings)
    except ValueError as exc:
        raise HTTPException(
            400, detail={"code": "invalid_provider_url", "message": str(exc)}
        ) from exc


def _schema_allowlists(
    schema: dict[str, Any],
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    return (
        {table["name"] for table in schema["tables"]},
        {table["schema"] for table in schema["tables"] if table.get("schema")},
        {
            table["name"]: {column["name"] for column in table["columns"]}
            for table in schema["tables"]
        },
    )


def _validate_and_ticket(payload: ValidateQueryRequest, services: Services) -> ValidationResult:
    _require_demo_database(payload.database_id, services)
    now = time.time()
    expired = [
        ticket_id for ticket_id, item in _validation_tickets.items() if item["expires"] < now
    ]
    for ticket_id in expired:
        _validation_tickets.pop(ticket_id, None)
    try:
        schema = services.databases.schema(payload.database_id)
    except KeyError as exc:
        raise HTTPException(
            404, detail={"code": "database_not_found", "message": str(exc)}
        ) from exc
    tables, schemas, columns = _schema_allowlists(schema)
    checked = services.validator.validate(payload.sql, schema["dialect"], tables, schemas, columns)
    if not checked.valid:
        logger.warning(
            "sql_validation_failed database_id=%s errors=%s",
            payload.database_id,
            len(checked.errors),
        )
        return ValidationResult(
            valid=False, referenced_tables=checked.tables, errors=checked.errors
        )
    ticket_id = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(seconds=TICKET_TTL_SECONDS)
    _validation_tickets[ticket_id] = {
        "database_id": payload.database_id,
        "sql": checked.normalized_sql,
        "digest": hashlib.sha256((checked.normalized_sql or "").encode()).hexdigest(),
        "expires": expires_at.timestamp(),
    }
    return ValidationResult(
        valid=True,
        normalized_sql=checked.normalized_sql,
        validation_id=ticket_id,
        referenced_tables=checked.tables,
        expires_at=expires_at,
    )


@router.get("/health")
def health(services: Services = Depends(get_services)) -> dict[str, Any]:
    response = {"status": "ok", "app": services.settings.app_name}
    if services.settings.public_demo_mode:
        response["mode"] = "public_demo"
    else:
        response["environment"] = services.settings.app_env
        response["mode"] = "local"
    return response


@router.get("/providers")
def providers(services: Services = Depends(get_services)) -> dict[str, Any]:
    settings = services.settings
    available = [
        {"id": "gemini", "name": "Google Gemini", "configured": bool(settings.gemini_api_key)},
        {"id": "groq", "name": "Groq", "configured": bool(settings.groq_api_key)},
        {"id": "openrouter", "name": "OpenRouter", "configured": bool(settings.openrouter_api_key)},
    ]
    if not settings.public_demo_mode:
        available.extend(
            [
                {
                    "id": "custom",
                    "name": settings.custom_llm_name,
                    "configured": bool(settings.custom_llm_api_key),
                },
                {"id": "ollama", "name": "Ollama (optional, local)", "configured": False},
            ]
        )
    return {
        "providers": available,
        "default_provider": settings.default_ai_provider,
        "default_model": settings.default_ai_model,
        "notice": "Free-tier eligibility and quotas are controlled by each provider and may change.",
    }


@router.post("/providers/test")
async def test_provider(
    payload: ProviderTestRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    provider = _provider(payload, services)
    try:
        models = await provider.models()
        available = not models or any(
            item.get("id", "").removeprefix("models/") == payload.model for item in models
        )
        return {"status": "ok", "model_available": available, "models_found": len(models)}
    except LLMError as exc:
        logger.warning("provider_test_failed provider=%s code=%s", payload.provider, exc.code)
        raise HTTPException(400, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/providers/models")
async def provider_models(
    payload: ProviderTestRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    provider = _provider(payload, services)
    try:
        models = await provider.models()
    except LLMError as exc:
        logger.warning("model_discovery_failed provider=%s code=%s", payload.provider, exc.code)
        raise HTTPException(400, detail={"code": exc.code, "message": str(exc)}) from exc
    compact_models = []
    for item in models:
        pricing = item.get("pricing") or {}
        compact = {
            "id": item.get("id") or item.get("name"),
            "name": item.get("name") or item.get("id"),
            "context_length": item.get("context_length") or item.get("context_window"),
        }
        if payload.provider == "openrouter":
            compact["pricing"] = {
                key: pricing.get(key) for key in ("prompt", "completion") if key in pricing
            }
            compact["is_free"] = bool(pricing) and all(
                str(pricing.get(key, "")) == "0" for key in ("prompt", "completion")
            )
        compact_models.append(compact)
    return {"models": compact_models}


@router.get("/databases")
def databases(services: Services = Depends(get_services)) -> dict[str, Any]:
    return {"databases": services.databases.list()}


@router.post("/databases/test")
def test_database(
    payload: DatabaseTestRequest, services: Services = Depends(get_services)
) -> dict[str, str]:
    _public_demo_denied(services, "External database testing")
    try:
        return services_for_test_database(payload)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "connection_failed", "message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("database_connection_test_failed dialect=%s", payload.dialect)
        raise HTTPException(
            400,
            detail={
                "code": "connection_failed",
                "message": "Connection failed. Verify the host, database, read-only credentials, and TLS settings.",
            },
        ) from exc


def services_for_test_database(payload: DatabaseTestRequest) -> dict[str, str]:
    from backend.app.services.database.manager import DatabaseManager

    return DatabaseManager.test_url(payload.dialect, payload.database_url.get_secret_value())


@router.post("/databases/connect", status_code=201)
def connect_database(
    payload: DatabaseConnectRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _public_demo_denied(services, "External database connections")
    try:
        return services.databases.connect(
            payload.name,
            payload.dialect,
            payload.database_url.get_secret_value(),
            payload.allowed_schemas,
        )
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "connection_failed", "message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("database_connection_failed dialect=%s", payload.dialect)
        raise HTTPException(
            400,
            detail={
                "code": "connection_failed",
                "message": "Connection failed. Verify the host, database, read-only credentials, and TLS settings.",
            },
        ) from exc


@router.delete("/databases/{database_id}")
def delete_database(
    database_id: str, services: Services = Depends(get_services)
) -> dict[str, bool]:
    _public_demo_denied(services, "Database connection changes")
    if not services.databases.remove(database_id):
        raise HTTPException(
            400, detail={"code": "cannot_remove", "message": "The connection cannot be removed."}
        )
    return {"deleted": True}


@router.get("/databases/{database_id}/schema")
def database_schema(
    database_id: str, refresh: bool = False, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _require_demo_database(database_id, services)
    try:
        return services.databases.schema(database_id, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(
            404, detail={"code": "database_not_found", "message": str(exc)}
        ) from exc


@router.get("/databases/{database_id}/preview/{table_name}")
def database_preview(
    database_id: str, table_name: str, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _require_demo_database(database_id, services)
    try:
        return {"rows": services.databases.preview(database_id, table_name)}
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, detail={"code": "preview_failed", "message": str(exc)}) from exc


@router.get("/query/examples")
def query_examples() -> dict[str, Any]:
    return {"examples": EXAMPLE_QUERIES, "generated_by_ai": False}


@router.post("/query/generate")
async def generate(
    payload: GenerateQueryRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _require_demo_database(payload.database_id, services)
    if payload.provider is None:
        raise HTTPException(
            400,
            detail={
                "code": "provider_required",
                "message": "Configure an AI provider or use a labeled example query.",
            },
        )
    provider = _provider(payload.provider, services)
    try:
        schema = services.databases.schema(payload.database_id)
        structured, usage = await generate_sql(
            provider,
            payload.question,
            schema,
            payload.conversation,
            services.settings.max_conversation_turns,
        )
    except LLMError as exc:
        logger.warning(
            "sql_generation_failed provider=%s model=%s code=%s",
            payload.provider.provider,
            payload.provider.model,
            exc.code,
        )
        raise HTTPException(400, detail={"code": exc.code, "message": str(exc)}) from exc
    validation = None
    if structured.sql:
        validation = _validate_and_ticket(
            ValidateQueryRequest(sql=structured.sql, database_id=payload.database_id), services
        )
    return {
        "analysis_id": services.corrections.start(),
        "generation": structured.model_dump(),
        "validation": validation,
        "usage": usage,
    }


@router.post("/query/validate", response_model=ValidationResult)
def validate_query(
    payload: ValidateQueryRequest, services: Services = Depends(get_services)
) -> ValidationResult:
    return _validate_and_ticket(payload, services)


@router.post("/query/execute", response_model=QueryResult)
def execute_query(
    payload: ExecuteQueryRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    ticket = _validation_tickets.pop(payload.validation_id, None)
    if not ticket or ticket["expires"] < time.time():
        raise HTTPException(
            400,
            detail={
                "code": "invalid_validation",
                "message": "Validation expired or was already used. Validate the SQL again.",
            },
        )
    actual_digest = hashlib.sha256(ticket["sql"].encode()).hexdigest()
    if not hmac.compare_digest(actual_digest, ticket["digest"]):
        logger.error("validation_ticket_integrity_failure")
        raise HTTPException(
            400,
            detail={
                "code": "invalid_validation",
                "message": "Validation ticket integrity check failed.",
            },
        )
    query_id = uuid4().hex
    try:
        result = services.executor.execute(ticket["database_id"], ticket["sql"])
        services.repository.record_history(
            id=query_id,
            question=payload.question,
            sql=ticket["sql"],
            database_id=ticket["database_id"],
            provider=payload.provider,
            model=payload.model,
            status="success",
            execution_time_ms=result["execution_time_ms"],
            row_count=result["row_count"],
        )
        logger.info(
            "query_executed query_id=%s database_id=%s duration_ms=%s rows=%s",
            query_id,
            ticket["database_id"],
            result["execution_time_ms"],
            result["row_count"],
        )
    except QueryExecutionError as exc:
        services.repository.record_history(
            id=query_id,
            question=payload.question,
            sql=ticket["sql"],
            database_id=ticket["database_id"],
            provider=payload.provider,
            model=payload.model,
            status="error",
            error=str(exc),
        )
        logger.warning(
            "query_execution_failed query_id=%s database_id=%s",
            query_id,
            ticket["database_id"],
        )
        raise HTTPException(
            400, detail={"code": "execution_failed", "message": str(exc), "query_id": query_id}
        ) from exc
    return {
        **result,
        "query_id": query_id,
        "chart": recommend_chart(result["rows"]),
        "summary": deterministic_summary(result["rows"]),
        "followups": suggest_followups(payload.question, result["rows"]),
    }


@router.post("/query/correct")
async def correct(
    payload: CorrectQueryRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _require_demo_database(payload.database_id, services)
    if not services.corrections.consume(payload.analysis_id):
        raise HTTPException(
            400,
            detail={
                "code": "correction_limit",
                "message": "The SQL correction limit was reached. Start a new analysis.",
            },
        )
    provider = _provider(payload.provider, services)
    try:
        structured = await correct_sql(
            provider,
            payload.question,
            payload.sql,
            payload.error,
            services.databases.schema(payload.database_id),
        )
    except LLMError as exc:
        raise HTTPException(400, detail={"code": exc.code, "message": str(exc)}) from exc
    validation = _validate_and_ticket(
        ValidateQueryRequest(sql=structured.sql, database_id=payload.database_id), services
    )
    return {
        "analysis_id": payload.analysis_id,
        "generation": structured.model_dump(),
        "validation": validation,
    }


@router.post("/query/explain")
async def explain(
    payload: ExplainQueryRequest, services: Services = Depends(get_services)
) -> dict[str, str]:
    local = deterministic_summary(payload.rows)
    if payload.provider is None:
        return {"explanation": local, "source": "deterministic"}
    provider = _provider(payload.provider, services)
    sample = payload.rows[:50]
    prompt = (
        "Explain these executed query results in plain English. Base every claim only on the supplied data. "
        "Mention assumptions, useful comparisons, and 2 follow-up questions. Do not output SQL.\n"
        f"Question: {payload.question}\nLocal statistics: {local}\nColumns: {payload.columns}\nRows: {json.dumps(sample, default=str)}"
    )
    try:
        response = await provider.complete(
            [
                {"role": "system", "content": "Return JSON with one string key named explanation."},
                {"role": "user", "content": prompt},
            ]
        )
        parsed = json.loads(
            response.text.strip().removeprefix("```json").removesuffix("```").strip()
        )
        return {"explanation": str(parsed["explanation"]), "source": "ai"}
    except (LLMError, json.JSONDecodeError, KeyError):
        return {"explanation": local, "source": "deterministic_fallback"}


@router.get("/query/history")
def history(
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None, max_length=200),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    _public_demo_denied(services, "Shared query history")
    return {"history": services.repository.history(limit, search)}


@router.get("/queries/saved")
def saved_queries(services: Services = Depends(get_services)) -> dict[str, Any]:
    _public_demo_denied(services, "Shared saved queries")
    return {"saved_queries": services.repository.saved()}


@router.post("/queries/saved", status_code=201)
def save_query(
    payload: SavedQueryCreate, services: Services = Depends(get_services)
) -> dict[str, Any]:
    _public_demo_denied(services, "Shared saved queries")
    return services.repository.create_saved(payload)


@router.delete("/queries/saved/{saved_id}")
def delete_saved(saved_id: str, services: Services = Depends(get_services)) -> dict[str, bool]:
    _public_demo_denied(services, "Shared saved queries")
    if not services.repository.delete_saved(saved_id):
        raise HTTPException(
            404, detail={"code": "not_found", "message": "Saved query was not found."}
        )
    return {"deleted": True}


@router.get("/overview")
def overview(services: Services = Depends(get_services)) -> dict[str, Any]:
    if services.settings.public_demo_mode:
        return {
            "stats": {
                "executed_queries": 0,
                "successful_queries": 0,
                "average_execution_ms": 0,
                "saved_queries": 0,
            },
            "recent_queries": [],
            "databases": services.databases.list(),
        }
    return {
        "stats": services.repository.stats(),
        "recent_queries": services.repository.history(5),
        "databases": services.databases.list(),
    }
