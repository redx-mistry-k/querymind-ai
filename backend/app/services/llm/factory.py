from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from backend.app.core.config import Settings
from backend.app.schemas.api import ProviderConfig
from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.providers import GeminiProvider, OpenAICompatibleProvider


def validate_custom_url(url: str, allow_local: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("Provider URL must be an HTTP(S) origin without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Provider URL cannot contain a query string or fragment.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("Provider hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        unsafe = (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        )
        if unsafe and not (allow_local and ip.is_loopback):
            raise ValueError("Private, local, and link-local provider addresses are blocked.")
    return url.rstrip("/")


def create_provider(config: ProviderConfig, settings: Settings) -> LLMProvider:
    api_key = config.api_key.get_secret_value() if config.api_key else ""
    common = {
        "model": config.model,
        "api_key": api_key,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if config.provider == "gemini":
        return GeminiProvider(**common)
    if config.provider == "groq":
        return OpenAICompatibleProvider("https://api.groq.com/openai/v1", **common)
    if config.provider == "openrouter":
        return OpenAICompatibleProvider(
            "https://openrouter.ai/api/v1",
            headers={"HTTP-Referer": "http://127.0.0.1", "X-Title": "QueryMind AI"},
            **common,
        )
    if config.provider == "ollama":
        base_url = (config.base_url or settings.ollama_base_url).rstrip("/")
        parsed = urlparse(base_url)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Ollama is restricted to the local machine.")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        return OpenAICompatibleProvider(base_url, **common)
    if not config.base_url:
        raise ValueError("A base URL is required for a custom provider.")
    base_url = validate_custom_url(config.base_url, settings.allow_local_custom_llm)
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return OpenAICompatibleProvider(base_url, **common)
