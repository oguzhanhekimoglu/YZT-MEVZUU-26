"""Local vLLM (OpenAI-compatible) structured-output client.

Aynı sözleşmeyi (BaseLLMClient) OllamaLLMClient ile paylaşır — bootstrap.py
config'teki llm_backend değerine göre ikisinden birini seçer, orchestrator
hangisinin çalıştığını bilmez/bilmesi gerekmez.
"""

from collections.abc import Sequence
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from operational_decision.contracts.llm import ollama_decision_json_schema
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError


class VLLMClient(BaseLLMClient):
    """Call one local vLLM (Docker, CUDA) model with schema-constrained JSON output."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:8003",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure a local-only endpoint and per-attempt timeout."""
        parsed_url = urlparse(base_url)
        if parsed_url.scheme != "http" or parsed_url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("vLLM base_url must be a local loopback endpoint")
        self.model = model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def generate(self, messages: Sequence[dict[str, str]]) -> str:
        """Perform exactly one chat request; callers own parse-only repair."""
        payload: dict[str, object] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": 800,
            "seed": 42,
            # vLLM uzantısı (outlines/lm-format-enforcer destekli) — Ollama'daki
            # "format": <json schema> ile aynı işi görür, şema dışı çıktı engellenir.
            "guided_json": ollama_decision_json_schema(),
        }
        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            choices = body.get("choices")
            if not isinstance(choices, list) or not choices:
                raise LocalLLMError("vLLM response is missing choices")
            message = choices[0].get("message")
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise LocalLLMError("vLLM response is missing message.content")
            return cast(str, message["content"])
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise LocalLLMError(f"vLLM request failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise LocalLLMError("vLLM response body is not valid JSON") from exc

    async def unload(self) -> None:
        """No-op: vLLM sunucu-ömrü boyunca modeli belleğe yükler, Ollama'nın
        keep_alive/unload semantiği vLLM'de karşılığı yok — model container
        durdurulana kadar açık kalır (bu kasıtlı, throughput için)."""
        return None

    async def aclose(self) -> None:
        """Close an internally owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()
