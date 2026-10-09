from __future__ import annotations

from typing import Any

from backend.app.services.llm.base import LLMError, LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self, base_url: str, *args: Any, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.extra_headers = headers or {}

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        response = await self._request(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "The provider returned an unexpected response.", "invalid_response"
            ) from exc
        return LLMResponse(text=content, usage=payload.get("usage"))

    async def models(self) -> list[dict[str, Any]]:
        response = await self._request("GET", f"{self.base_url}/models", headers=self.headers)
        return response.json().get("data", [])


class GeminiProvider(LLMProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    async def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        system_parts = [item["content"] for item in messages if item["role"] == "system"]
        contents = [
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in messages
            if item["role"] != "system"
        ]
        response = await self._request(
            "POST",
            f"{self.BASE_URL}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": "\n".join(system_parts)}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": self.temperature,
                    "maxOutputTokens": self.max_tokens,
                    "responseMimeType": "application/json",
                },
            },
        )
        payload = response.json()
        try:
            content = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Gemini returned no usable response.", "invalid_response") from exc
        return LLMResponse(text=content, usage=payload.get("usageMetadata"))

    async def models(self) -> list[dict[str, Any]]:
        response = await self._request(
            "GET", f"{self.BASE_URL}/models", headers={"x-goog-api-key": self.api_key}
        )
        return [
            {"id": item.get("name", "").removeprefix("models/"), "name": item.get("displayName")}
            for item in response.json().get("models", [])
            if "generateContent" in item.get("supportedGenerationMethods", [])
        ]
