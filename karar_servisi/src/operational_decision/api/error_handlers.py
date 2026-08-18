"""Sanitized API exception handlers."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from operational_decision.api.validation_messages import turkish_validation_errors
from operational_decision.memory.event_service import DuplicateProcessingError


def register_error_handlers(app: FastAPI) -> None:
    """Register controlled duplicate and unexpected-error mappings."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content={
                "detail": "VALIDATION_ERROR",
                "validation_errors": turkish_validation_errors(error.errors()),
            },
        )
    @app.exception_handler(DuplicateProcessingError)
    async def duplicate_handler(request: Request, error: DuplicateProcessingError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=409,
            content={
                "detail": "DUPLICATE_ACTIVE_EVENT",
                "event_id": error.existing_event_id,
            },
        )
