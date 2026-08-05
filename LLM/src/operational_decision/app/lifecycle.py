"""FastAPI startup and shutdown lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from operational_decision.app.bootstrap import build_application_container


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build dependencies lazily and close the owned Ollama HTTP client."""
    if getattr(app.state, "container", None) is None:
        app.state.container = await build_application_container()
    try:
        yield
    finally:
        client = app.state.container.orchestrator.deps.llm_client
        close = getattr(client, "aclose", None)
        if callable(close):
            await close()
