"""Application health HTTP adapter."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from operational_decision.api.dependencies import get_container
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.health import HealthStatus

router = APIRouter()


@router.get("/health")
async def health(
    container: Annotated[ApplicationContainer, Depends(get_container)],
    deep: bool = False,
) -> JSONResponse:
    """Return deterministic component aggregation and HTTP status."""
    report = await container.health_service.check(deep=deep)
    return JSONResponse(
        status_code=503 if report.status is HealthStatus.FAILED else 200,
        content=report.model_dump(mode="json"),
    )
