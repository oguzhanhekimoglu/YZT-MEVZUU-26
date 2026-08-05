"""Explicitly unload the configured local Ollama model."""

import asyncio

from operational_decision.llm.ollama_client import OllamaLLMClient


async def _main() -> None:
    client = OllamaLLMClient()
    try:
        await client.unload()
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(_main())