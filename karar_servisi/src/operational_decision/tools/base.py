"""Shared execution envelope, timeout, error mapping, retry, and audit behavior."""

import asyncio
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from time import perf_counter
from typing import Generic, TypeVar, cast

from pydantic import BaseModel

from operational_decision.contracts.common import ToolExecutionStatus
from operational_decision.contracts.tools import ToolError, ToolResponseEnvelope
from operational_decision.memory.event_service import EventService
from operational_decision.persistence.sqlite_database import utc_now

RequestT = TypeVar("RequestT", bound=BaseModel)
DataT = TypeVar("DataT", bound=BaseModel)


class ToolExecutionFailure(Exception):
    """Carry a sanitized, non-retryable-by-default controlled tool failure."""

    def __init__(self, *, code: str, message: str, retryable: bool = False) -> None:
        """Store the controlled error fields exposed by the tool envelope."""
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class ToolSkipped(Exception):
    """Carry a reasoned domain result for a deliberately skipped tool."""

    def __init__(self, data: BaseModel, reason: str) -> None:
        """Store the skipped domain result and its controlled reason."""
        self.data = data
        self.reason = reason
        super().__init__(reason)


def _sqlite_error_code(error: sqlite3.OperationalError) -> str:
    message = str(error).casefold()
    if "locked" in message:
        return "SQLITE_LOCKED"
    if "busy" in message:
        return "SQLITE_BUSY"
    return "SQLITE_ERROR"


class BaseTool(Generic[RequestT, DataT], ABC):
    """Execute a controlled tool with separate infrastructure and domain states."""

    tool_name: str
    tool_version = "1.0.0"

    def __init__(
        self,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> None:
        """Set stable envelope identifiers and optional durable audit storage."""
        self.event_id = event_id
        self.request_id = request_id
        self.event_service = event_service

    async def execute(
        self,
        request: RequestT,
        *,
        timeout_seconds: float,
    ) -> ToolResponseEnvelope[DataT]:
        """Execute once, retrying only one transient SQLite failure."""
        try:
            self.validate_request(request)
            if timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be greater than zero")
        except (TypeError, ValueError) as error:
            return await self._failure_envelope(
                request,
                ToolExecutionStatus.INVALID_INPUT,
                "INVALID_INPUT",
                str(error),
                retryable=False,
                attempt_number=1,
            )

        for attempt_number in (1, 2):
            started_at = utc_now()
            timer = perf_counter()
            try:
                data = await asyncio.wait_for(
                    self.execute_internal(request), timeout=timeout_seconds
                )
            except ToolSkipped as skipped:
                return await self._success_envelope(
                    request,
                    cast(DataT, skipped.data),
                    ToolExecutionStatus.SKIPPED,
                    started_at,
                    timer,
                    attempt_number,
                    warnings=[skipped.reason],
                )
            except ToolExecutionFailure as error:
                return await self._failure_envelope(
                    request,
                    ToolExecutionStatus.ERROR,
                    error.code,
                    error.message,
                    retryable=error.retryable,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    timer=timer,
                )
            except TimeoutError:
                return await self._failure_envelope(
                    request,
                    ToolExecutionStatus.TIMEOUT,
                    "TIMEOUT",
                    "tool execution timed out",
                    retryable=False,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    timer=timer,
                )
            except sqlite3.OperationalError as error:
                code = _sqlite_error_code(error)
                transient = code in {"SQLITE_BUSY", "SQLITE_LOCKED"}
                envelope = await self._failure_envelope(
                    request,
                    ToolExecutionStatus.ERROR,
                    code,
                    "transient SQLite failure" if transient else "SQLite failure",
                    retryable=transient and attempt_number == 1,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    timer=timer,
                )
                if transient and attempt_number == 1:
                    continue
                return envelope
            except (TypeError, ValueError) as error:
                return await self._failure_envelope(
                    request,
                    ToolExecutionStatus.INVALID_INPUT,
                    "INVALID_INPUT",
                    str(error),
                    retryable=False,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    timer=timer,
                )
            except Exception:
                return await self._failure_envelope(
                    request,
                    ToolExecutionStatus.ERROR,
                    "TOOL_ERROR",
                    "tool execution failed",
                    retryable=False,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    timer=timer,
                )
            return await self._success_envelope(
                request,
                data,
                ToolExecutionStatus.SUCCESS,
                started_at,
                timer,
                attempt_number,
            )
        raise RuntimeError("unreachable retry state")

    def validate_request(self, request: RequestT) -> None:
        """Validate tool-specific invariants beyond the strict request model."""

    @abstractmethod
    async def execute_internal(self, request: RequestT) -> DataT:
        """Execute domain behavior without wrapping infrastructure concerns."""

    async def _success_envelope(
        self,
        request: RequestT,
        data: DataT,
        status: ToolExecutionStatus,
        started_at: datetime,
        timer: float,
        attempt_number: int,
        warnings: list[str] | None = None,
    ) -> ToolResponseEnvelope[DataT]:
        finished_at = utc_now()
        latency = max(0, round((perf_counter() - timer) * 1000))
        envelope = ToolResponseEnvelope[DataT](
            tool_name=self.tool_name,
            tool_version=self.tool_version,
            event_id=self.event_id,
            request_id=self.request_id,
            execution_status=status,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            latency_ms=latency,
            data=data,
            warnings=warnings or [],
            source_refs=self._source_refs(data),
        )
        await self._audit(request, envelope, attempt_number, self._domain_status(data))
        return envelope

    async def _failure_envelope(
        self,
        request: RequestT,
        status: ToolExecutionStatus,
        code: str,
        message: str,
        *,
        retryable: bool,
        attempt_number: int,
        started_at: datetime | None = None,
        timer: float | None = None,
    ) -> ToolResponseEnvelope[DataT]:
        actual_start = utc_now() if started_at is None else started_at
        finished_at = utc_now()
        latency = 0 if timer is None else max(0, round((perf_counter() - timer) * 1000))
        envelope = ToolResponseEnvelope[DataT](
            tool_name=self.tool_name,
            tool_version=self.tool_version,
            event_id=self.event_id,
            request_id=self.request_id,
            execution_status=status,
            started_at_utc=actual_start,
            finished_at_utc=finished_at,
            latency_ms=latency,
            error=ToolError(code=code, message=message, retryable=retryable),
        )
        await self._audit(request, envelope, attempt_number, None)
        return envelope

    async def _audit(
        self,
        request: RequestT,
        envelope: ToolResponseEnvelope[DataT],
        attempt_number: int,
        domain_status: str | None,
    ) -> None:
        if self.event_service is None:
            return
        await self.event_service.record_tool_execution(
            event_id=self.event_id,
            request_id=self.request_id,
            tool_name=self.tool_name,
            attempt_number=attempt_number,
            execution_status=envelope.execution_status.value,
            domain_status=domain_status,
            request=request.model_dump(mode="json"),
            response=envelope.model_dump(mode="json"),
            latency_ms=envelope.latency_ms,
            error_code=envelope.error.code if envelope.error else None,
        )

    @staticmethod
    def _source_refs(data: DataT) -> list[str]:
        sources = getattr(data, "sources", [])
        return [str(source.source_id) for source in sources]

    @staticmethod
    def _domain_status(data: DataT) -> str | None:
        for field_name in ("platform_status", "permission_status", "notam_status"):
            value = getattr(data, field_name, None)
            if value is not None:
                return str(value)
        return None
