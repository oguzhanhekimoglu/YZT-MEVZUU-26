"""FastAPI dependency accessors."""

from fastapi import Request

from operational_decision.app.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    """Return the initialized application container."""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("application container is not initialized")
    return container
