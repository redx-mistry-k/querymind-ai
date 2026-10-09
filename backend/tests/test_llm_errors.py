from __future__ import annotations

import httpx
import pytest

from backend.app.services.llm import base
from backend.app.services.llm.base import LLMError
from backend.app.services.llm.providers import OpenAICompatibleProvider


def mocked_client(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(base.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_invalid_api_key_is_classified(monkeypatch):
    mocked_client(
        monkeypatch,
        lambda request: httpx.Response(401, json={"error": "invalid key"}, request=request),
    )
    provider = OpenAICompatibleProvider("https://provider.example/v1", model="test", api_key="bad")
    with pytest.raises(LLMError) as error:
        await provider.models()
    assert error.value.code == "invalid_key"
    assert "key" in str(error.value).lower()


@pytest.mark.asyncio
async def test_rate_limit_retries_are_bounded(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": "quota"}, request=request)

    async def no_wait(_):
        return None

    mocked_client(monkeypatch, handler)
    monkeypatch.setattr(base.asyncio, "sleep", no_wait)
    provider = OpenAICompatibleProvider("https://provider.example/v1", model="test", api_key="key")
    with pytest.raises(LLMError) as error:
        await provider.models()
    assert error.value.code == "rate_limit"
    assert calls == 3


@pytest.mark.asyncio
async def test_invalid_model_request_is_not_exposed_as_server_error(monkeypatch):
    mocked_client(
        monkeypatch,
        lambda request: httpx.Response(
            400, json={"error": "internal provider detail"}, request=request
        ),
    )
    provider = OpenAICompatibleProvider(
        "https://provider.example/v1", model="missing", api_key="key"
    )
    with pytest.raises(LLMError) as error:
        await provider.models()
    assert error.value.code == "invalid_request"
    assert "internal provider detail" not in str(error.value)


@pytest.mark.asyncio
async def test_transient_provider_failures_have_bounded_retries(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    async def no_wait(_):
        return None

    mocked_client(monkeypatch, handler)
    monkeypatch.setattr(base.asyncio, "sleep", no_wait)
    provider = OpenAICompatibleProvider("https://provider.example/v1", model="test", api_key="key")
    with pytest.raises(LLMError) as error:
        await provider.models()
    assert error.value.code == "provider_unavailable"
    assert calls == 3
