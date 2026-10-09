from __future__ import annotations

import hmac
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.dependencies import Services
from backend.app.api.v1 import router
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging
from backend.app.core.rate_limit import SessionRateLimiter
from backend.app.repositories.metadata import MetadataRepository
from backend.app.services.database.demo import create_demo_database
from backend.app.services.database.executor import QueryExecutor
from backend.app.services.database.manager import DatabaseManager
from backend.app.services.sql.generator import CorrectionBudget
from backend.app.services.sql.validator import SQLValidator


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or get_settings()
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if (
        settings.app_host not in loopback_hosts or settings.public_demo_mode
    ) and not settings.api_access_token:
        raise RuntimeError(
            "QUERYMIND_API_TOKEN is required for public demo mode or a non-loopback bind."
        )
    configure_logging(settings.log_level)
    max_query_rows = (
        min(settings.max_query_rows, settings.public_demo_max_query_rows)
        if settings.public_demo_mode
        else settings.max_query_rows
    )
    query_timeout_seconds = (
        min(settings.query_timeout_seconds, settings.public_demo_query_timeout_seconds)
        if settings.public_demo_mode
        else settings.query_timeout_seconds
    )
    limiter = SessionRateLimiter()

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        create_demo_database(settings.demo_db_path)
        repository = MetadataRepository(str(settings.metadata_db_path))
        databases = DatabaseManager(settings, repository)
        databases.add_demo()
        lifespan_app.state.services = Services(
            settings=settings,
            repository=repository,
            databases=databases,
            validator=SQLValidator(max_query_rows),
            executor=QueryExecutor(databases, query_timeout_seconds, max_query_rows),
            corrections=CorrectionBudget(settings.max_sql_retries),
        )
        yield

    application = FastAPI(
        title="QueryMind AI API",
        description="Local-first, read-only natural-language SQL analytics API.",
        version="0.2.0",
        docs_url=None if settings.public_demo_mode else "/docs",
        redoc_url=None if settings.public_demo_mode else "/redoc",
        openapi_url=None if settings.public_demo_mode else "/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-QueryMind-Session"],
    )

    @application.middleware("http")
    async def require_api_token(request: Request, call_next):
        if request.url.path.startswith("/api/v1") and settings.api_access_token:
            authorization = request.headers.get("Authorization", "")
            expected = f"Bearer {settings.api_access_token}"
            if not hmac.compare_digest(authorization, expected):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "unauthorized",
                            "message": "A valid API access token is required.",
                        }
                    },
                )
        if request.url.path.startswith("/api/v1") and settings.public_demo_mode:
            supplied_session = request.headers.get("X-QueryMind-Session", "")
            if re.fullmatch(r"[A-Za-z0-9_-]{16,64}", supplied_session):
                session_id = supplied_session
            else:
                session_id = request.client.host if request.client else "unknown"
            checks = [
                (
                    "all",
                    settings.public_demo_requests_per_minute,
                    None,
                )
            ]
            if request.url.path in {
                "/api/v1/providers/test",
                "/api/v1/providers/models",
                "/api/v1/query/generate",
                "/api/v1/query/correct",
                "/api/v1/query/explain",
            }:
                checks.append(
                    (
                        "llm",
                        settings.public_demo_llm_calls_per_minute,
                        settings.public_demo_llm_calls_per_session,
                    )
                )
            if request.url.path == "/api/v1/query/execute":
                checks.append(("execution", settings.public_demo_executions_per_minute, None))
            for bucket, per_minute, total in checks:
                decision = limiter.check(
                    session_id,
                    bucket,
                    max(1, per_minute),
                    total_limit=max(1, total) if total is not None else None,
                )
                if not decision.allowed:
                    return JSONResponse(
                        status_code=429,
                        headers={"Retry-After": str(decision.retry_after)},
                        content={
                            "detail": {
                                "code": "demo_rate_limit",
                                "message": "The public demo limit was reached. Wait before trying again.",
                            }
                        },
                    )
        return await call_next(request)

    application.include_router(router)

    @application.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        # The detailed exception is logged by the server; clients receive no traceback or secrets.
        import logging

        logging.getLogger(__name__).exception("Unhandled request error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                }
            },
        )

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        result = {"name": "QueryMind AI", "health": "/api/v1/health"}
        if not settings.public_demo_mode:
            result["docs"] = "/docs"
        return result

    return application


app = create_app()
