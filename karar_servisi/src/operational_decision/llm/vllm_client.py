"""OpenAI-uyumlu (vLLM/EVREN) yapılandırılmış-çıktı istemcisi.

Tek allowed local LLM transport (BaseLLMClient) — TEKNOFEST TYDA için SSB'nin
sağladığı EVREN çıkarım servisine (https://evren-llmapi.ssyz.org.tr) veya
kendi barındırılan bir vLLM sunucusuna bağlanır, wire formatı ikisi için de
aynı (OpenAI /v1/chat/completions).
"""

from collections.abc import Sequence
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from operational_decision.contracts.llm import ollama_decision_json_schema
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError


class VLLMClient(BaseLLMClient):
    """Call one OpenAI-compatible model (EVREN veya kendi barındırılan vLLM) with schema-constrained JSON output."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:8003",
        api_key: str | None = None,
        timeout_seconds: float = 1800.0,  # EVREN dokumantasyonu: chat completions icin zorunlu
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the endpoint, opsiyonel API anahtarı ve per-attempt timeout.

        Şifresiz (http://) bağlantı yalnızca loopback'te kabul edilir — uzak bir
        host'a düz http:// ile bağlanmaya çalışmak (kazara şifresiz istek) burada
        engellenir. Uzak/paylaşımlı bir uç nokta (EVREN gibi) https:// gerektirir.
        """
        parsed_url = urlparse(base_url)
        is_loopback_http = parsed_url.scheme == "http" and parsed_url.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
        if not (is_loopback_http or parsed_url.scheme == "https"):
            raise ValueError("vLLM base_url must be a loopback http:// endpoint or any https:// endpoint")
        self.model = model
        self._owns_client = client is None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, headers=headers)

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        response_schema: dict[str, object] | None = None,
        max_tokens: int = 800,
    ) -> str:
        """Perform exactly one chat request; callers own parse-only repair."""
        payload: dict[str, object] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": max_tokens,
            "seed": 42,
            # BUG-FIX: ana pipeline'in spike testinde dogrulandi - "llm-fast"
            # reasoning'i chat_template_kwargs.enable_thinking=False ile
            # kapatinca ayni dogru sonucu %92 daha az token'la, hic
            # reasoning_content uretmeden veriyor.
            "chat_template_kwargs": {"enable_thinking": False},
            # OpenAI standart yapılandırılmış çıktı sözleşmesi — şema dışı çıktı engellenir.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "operational_decision",
                    "schema": response_schema or ollama_decision_json_schema(),
                    "strict": True,
                },
            },
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
        except httpx.HTTPStatusError as exc:
            body_snippet = exc.response.text[:300]
            raise LocalLLMError(
                f"vLLM request failed: HTTPStatusError status={exc.response.status_code} "
                f"body={body_snippet!r}"
            ) from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
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
