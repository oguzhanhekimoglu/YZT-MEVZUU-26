"""Stub-server smoke coverage for the native local Ollama client."""
# ruff: noqa: D103

import json

import httpx
import pytest

from operational_decision.contracts.common import DecisionCode
from operational_decision.contracts.llm import LLMDecision, ollama_decision_json_schema
from operational_decision.llm.ollama_client import OllamaLLMClient


@pytest.mark.asyncio
async def test_stub_ollama_chat_schema_keep_alive_and_unload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/chat":
            content = LLMDecision(
                decision_code=DecisionCode.INDETERMINATE,
                summary_tr="Stub smoke başarılı.",
            ).model_dump_json()
            return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
        return httpx.Response(200, json={"done": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434"
    ) as http:
        client = OllamaLLMClient(client=http)
        raw = await client.generate([{"role": "user", "content": "{}"}])
        await client.unload()

    assert LLMDecision.model_validate_json(raw).summary_tr == "Stub smoke başarılı."
    chat_payload = json.loads(requests[0].content)
    unload_payload = json.loads(requests[1].content)
    assert chat_payload["format"] == ollama_decision_json_schema()
    assert chat_payload["keep_alive"] == "10m"
    assert chat_payload["think"] is False
    assert chat_payload["stream"] is False
    assert chat_payload["options"] == {
        "num_ctx": 8192,
        "num_predict": 800,
        "temperature": 0.1,
        "top_p": 0.8,
        "seed": 42,
    }
    assert unload_payload["keep_alive"] == 0
