"""Environment-aware real local Ollama acceptance smoke."""

import asyncio
from enum import StrEnum

import httpx
from pydantic import Field

from operational_decision.contracts.common import StrictContract
from operational_decision.contracts.llm import LLMDecision
from operational_decision.llm.ollama_client import OllamaLLMClient

CANONICAL_MODEL = "llama3.2:1b"


class RealSmokeStatus(StrEnum):
    """Explicit real-smoke outcomes without pytest skipping."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_RUN_ENVIRONMENT_MISSING = "NOT_RUN_ENVIRONMENT_MISSING"


class RealOllamaSmokeResult(StrictContract):
    """Machine-readable real Ollama smoke report."""

    status: RealSmokeStatus
    model: str
    chat_called: bool = False
    parsed: bool = False
    stream: bool = False
    think: bool = False
    keep_alive: str = "10m"
    unload_requested: bool = False
    unload_observed: bool | None = None
    detail: str | None = Field(default=None, max_length=300)


async def run_real_ollama_smoke(
    *, base_url: str = "http://127.0.0.1:11434"
) -> RealOllamaSmokeResult:
    """Run only when localhost and the canonical model already exist."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=3.0) as http:
            tags = await http.get("/api/tags")
            tags.raise_for_status()
            payload = tags.json()
    except Exception:
        return RealOllamaSmokeResult(
            status=RealSmokeStatus.NOT_RUN_ENVIRONMENT_MISSING,
            model=CANONICAL_MODEL,
            detail="OLLAMA_LOCALHOST_UNAVAILABLE",
        )
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = {
        value
        for item in models
        if isinstance(item, dict)
        for value in (item.get("name"), item.get("model"))
        if isinstance(value, str)
    }
    if CANONICAL_MODEL not in names:
        return RealOllamaSmokeResult(
            status=RealSmokeStatus.NOT_RUN_ENVIRONMENT_MISSING,
            model=CANONICAL_MODEL,
            detail="CANONICAL_MODEL_MISSING",
        )

    client = OllamaLLMClient(
        model=CANONICAL_MODEL,
        base_url=base_url,
        keep_alive="10m",
        timeout_seconds=120.0,
    )
    unload_requested = False
    try:
        raw = await client.generate(
            [
                {
                    "role": "user",
                    "content": (
                        "Return only valid JSON: decision_code INDETERMINATE, "
                        "summary_tr as a short Turkish sentence, and empty lists for "
                        "evidence_summary, recommended_actions, uncertainty_notes, source_ids."
                    ),
                }
            ]
        )
        LLMDecision.model_validate_json(raw, strict=True)
        await client.unload()
        unload_requested = True
        unload_observed: bool | None = None
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=3.0) as http:
                for _ in range(10):
                    running = await http.get("/api/ps")
                    running.raise_for_status()
                    body = running.json()
                    loaded = body.get("models", []) if isinstance(body, dict) else []
                    loaded_names = {
                        value
                        for item in loaded
                        if isinstance(item, dict)
                        for value in (item.get("name"), item.get("model"))
                        if isinstance(value, str)
                    }
                    if CANONICAL_MODEL not in loaded_names:
                        unload_observed = True
                        break
                    await asyncio.sleep(0.25)
                else:
                    unload_observed = False
        except Exception:
            unload_observed = None
        return RealOllamaSmokeResult(
            status=RealSmokeStatus.PASSED,
            model=CANONICAL_MODEL,
            chat_called=True,
            parsed=True,
            unload_requested=True,
            unload_observed=unload_observed,
        )
    except Exception as error:
        return RealOllamaSmokeResult(
            status=RealSmokeStatus.FAILED,
            model=CANONICAL_MODEL,
            chat_called=True,
            unload_requested=unload_requested,
            detail=type(error).__name__,
        )
    finally:
        await client.aclose()
