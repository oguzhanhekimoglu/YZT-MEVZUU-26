"""Native local Ollama structured-output client."""

from collections.abc import Sequence
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from operational_decision.contracts.llm import ollama_decision_json_schema
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError


class OllamaLLMClient(BaseLLMClient):
    """Call one local Ollama model with schema-constrained JSON output."""

    def __init__(
        self,
        *,
        model: str = "llama3.2:1b",
        base_url: str = "http://127.0.0.1:11434",
        keep_alive: str = "10m",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure a local-only endpoint, model lifetime, and per-attempt timeout."""
        parsed_url = urlparse(base_url)
        if parsed_url.scheme != "http" or parsed_url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Ollama base_url must be a local loopback endpoint")
        self.model = model
        self._keep_alive = keep_alive
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def generate(self, messages: Sequence[dict[str, str]]) -> str:
        """Perform exactly one chat request; callers own parse-only repair."""
        payload: dict[str, object] = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
            "think": False,
            "format": ollama_decision_json_schema(),
            "keep_alive": self._keep_alive,
            "options": {
                "num_ctx": 8192,
                "num_predict": 800,
                "temperature": 0.1,
                "top_p": 0.8,
                "seed": 42,
            },
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            message = body.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise LocalLLMError("Ollama response is missing message.content")
            return cast(str, message["content"])
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise LocalLLMError(f"Ollama request failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise LocalLLMError("Ollama response body is not valid JSON") from exc

    async def unload(self) -> None:
        """Request immediate unload; lifecycle call timing is owned by Phase 7."""
        try:
            response = await self._client.post(
                "/api/generate",
                json={"model": self.model, "prompt": "", "stream": False, "keep_alive": 0},
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise LocalLLMError(f"Ollama unload failed: {type(exc).__name__}") from exc

    async def aclose(self) -> None:
        """Close an internally owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()
