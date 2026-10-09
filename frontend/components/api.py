from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any

import httpx

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
API_TOKEN = os.getenv("QUERYMIND_API_TOKEN", "")
_SESSION_ID: ContextVar[str] = ContextVar("querymind_session_id", default="")


class APIError(RuntimeError):
    pass


def set_session_id(session_id: str) -> None:
    _SESSION_ID.set(session_id)


def request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        with httpx.Client(timeout=35) as client:
            headers = kwargs.pop("headers", {})
            if API_TOKEN:
                headers["Authorization"] = f"Bearer {API_TOKEN}"
            if session_id := _SESSION_ID.get():
                headers["X-QueryMind-Session"] = session_id
            response = client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise APIError(
            "The local API is unavailable. Start QueryMind with `python run.py`."
        ) from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", {})
            message = detail.get("message", detail) if isinstance(detail, dict) else detail
        except ValueError:
            message = response.text
        raise APIError(str(message or f"Request failed ({response.status_code})."))
    return response.json()


def get(path: str, **params: Any) -> Any:
    return request("GET", path, params=params)


def post(path: str, payload: dict[str, Any]) -> Any:
    return request("POST", path, json=payload)


def delete(path: str) -> Any:
    return request("DELETE", path)
