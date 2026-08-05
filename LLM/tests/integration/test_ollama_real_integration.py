"""Environment-aware real canonical Ollama integration acceptance."""
# ruff: noqa: D103

import pytest

from operational_decision.llm.real_smoke import (
    RealSmokeStatus,
    run_real_ollama_smoke,
)


@pytest.mark.asyncio
async def test_real_canonical_ollama_or_reports_environment_missing() -> None:
    result = await run_real_ollama_smoke()
    assert result.status is not RealSmokeStatus.FAILED, result.detail
    if result.status is RealSmokeStatus.NOT_RUN_ENVIRONMENT_MISSING:
        assert result.detail in {
            "OLLAMA_LOCALHOST_UNAVAILABLE",
            "CANONICAL_MODEL_MISSING",
        }
        return
    assert result.chat_called is True
    assert result.parsed is True
    assert result.stream is False
    assert result.think is False
    assert result.keep_alive == "10m"
    assert result.unload_requested is True
    assert result.unload_observed in {True, None}
