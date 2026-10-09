from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, Any] | None = None


class LLMProvider(abc.ABC):
    def __init__(
        self, model: str, api_key: str = "", temperature: float = 0.1, max_tokens: int = 1000
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abc.abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        raise NotImplementedError

    async def models(self) -> list[dict[str, Any]]:
        return []

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            for attempt in range(3):
                try:
                    response = await client.request(method, url, **kwargs)
                    if response.status_code == 429:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * (2**attempt))
                            continue
                        raise LLMError(
                            "The provider rate limit or quota was reached. Wait for the quota to reset or select another model intentionally.",
                            "rate_limit",
                        )
                    if response.status_code in {401, 403}:
                        raise LLMError(
                            "The provider rejected the API key or access permissions.",
                            "invalid_key",
                        )
                    if response.status_code == 404:
                        raise LLMError(
                            "The selected model or provider endpoint is unavailable.",
                            "model_unavailable",
                        )
                    if response.status_code in {408, 409, 425, 500, 502, 503, 504}:
                        if attempt < 2:
                            logger.warning(
                                "provider_transient_error status=%s attempt=%s",
                                response.status_code,
                                attempt + 1,
                            )
                            await asyncio.sleep(0.5 * (2**attempt))
                            continue
                        raise LLMError(
                            "The provider is temporarily unavailable after bounded retries.",
                            "provider_unavailable",
                        )
                    if response.status_code in {400, 422}:
                        raise LLMError(
                            "The provider rejected the request. Verify the model identifier and compatibility.",
                            "invalid_request",
                        )
                    if response.is_error:
                        raise LLMError(
                            f"The provider returned HTTP {response.status_code}.",
                            "provider_error",
                        )
                    response.raise_for_status()
                    return response
                except LLMError:
                    raise
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue
            raise LLMError(f"The provider request failed: {last_error}", "network_error")
