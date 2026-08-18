"""Run the environment-aware canonical real Ollama smoke."""

import asyncio

from operational_decision.llm.real_smoke import RealSmokeStatus, run_real_ollama_smoke


async def _main() -> int:
    result = await run_real_ollama_smoke()
    print(result.model_dump_json(indent=2))
    return 1 if result.status is RealSmokeStatus.FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
