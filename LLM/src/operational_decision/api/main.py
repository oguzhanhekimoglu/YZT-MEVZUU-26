"""FastAPI application factory for the operational decision subsystem."""

from fastapi import FastAPI

from operational_decision.api.error_handlers import register_error_handlers
from operational_decision.api.routes_adapters import router as adapters_router
from operational_decision.api.routes_events import router as events_router
from operational_decision.api.routes_health import router as health_router
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.lifecycle import application_lifespan


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Create the HTTP adapter with optional test/embedded dependencies."""
    application = FastAPI(
        title="Operational Decision API",
        version="2.0",
        lifespan=application_lifespan,
    )
    if container is not None:
        application.state.container = container
    application.include_router(adapters_router)
    application.include_router(events_router)
    application.include_router(health_router)
    register_error_handlers(application)
    return application


app = create_app()
