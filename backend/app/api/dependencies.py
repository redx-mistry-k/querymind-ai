from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from backend.app.core.config import Settings
from backend.app.repositories.metadata import MetadataRepository
from backend.app.services.database.executor import QueryExecutor
from backend.app.services.database.manager import DatabaseManager
from backend.app.services.sql.generator import CorrectionBudget
from backend.app.services.sql.validator import SQLValidator


@dataclass
class Services:
    settings: Settings
    repository: MetadataRepository
    databases: DatabaseManager
    validator: SQLValidator
    executor: QueryExecutor
    corrections: CorrectionBudget


def get_services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise RuntimeError("Application services have not been initialized.")
    return services
