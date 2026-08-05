"""Structured safe logging facade for event operations."""

import structlog


class EventLogger:
    """Emit required identifiers without raw evidence or local paths."""

    def __init__(self) -> None:
        """Bind the project logger."""
        self._logger = structlog.get_logger("operational_decision")

    def info(
        self,
        *,
        event_id: str,
        request_id: str,
        operation: str,
        status: str,
        latency_ms: int | None = None,
    ) -> None:
        """Emit one sanitized successful operation record."""
        self._logger.info(
            operation,
            event_id=event_id,
            request_id=request_id,
            module="decision_orchestrator",
            status=status,
            latency_ms=latency_ms,
            error_code=None,
        )

    def warning(self, *, event_id: str, request_id: str, operation: str, error_code: str) -> None:
        """Emit one sanitized warning record."""
        self._logger.warning(
            operation,
            event_id=event_id,
            request_id=request_id,
            module="decision_orchestrator",
            status="WARNING",
            latency_ms=None,
            error_code=error_code,
        )
