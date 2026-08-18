"""Controlled Turkey Inventory V1 lookup tool."""

from pathlib import Path

from operational_decision.contracts.common import (
    InventoryStatus,
    PlatformStatus,
    ToolExecutionStatus,
)
from operational_decision.contracts.inventory import (
    TurkeyInventoryResult,
    TurkeyInventoryToolRequest,
)
from operational_decision.contracts.platform import PlatformRegistry
from operational_decision.contracts.tools import ToolError, ToolResponseEnvelope
from operational_decision.inventory.turkey_inventory_registry import (
    TurkeyInventoryRegistry,
    TurkeyInventoryRegistryError,
    load_turkey_inventory_registry,
)
from operational_decision.memory.event_service import EventService
from operational_decision.persistence.sqlite_database import utc_now
from operational_decision.tools.base import BaseTool, ToolSkipped

_NOT_LISTED_MESSAGE = "Platform mevcut Türkiye envanter veri setinde bulunamadı."
_UNKNOWN_MESSAGE = "Türkiye envanter kontrolü tamamlanamadı."
_NOT_APPLICABLE_MESSAGE = "Türkiye envanter kontrolü hava aracı olmayan hedefe uygulanmaz."
_CONFIRMED_MESSAGE = (
    "Platform mevcut Türkiye envanter veri setinde doğrulandı; bu sonuç uçuş izni anlamına gelmez."
)


class TurkeyInventoryTool(BaseTool[TurkeyInventoryToolRequest, TurkeyInventoryResult]):
    """Resolve Inventory scope only through an exact platform identifier."""

    tool_name = "turkey_inventory_tool"
    tool_version = "1.0.0"

    def __init__(
        self,
        registry: TurkeyInventoryRegistry | None,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
        registry_error: TurkeyInventoryRegistryError | None = None,
    ) -> None:
        """Bind a loaded registry or an explicit registry load failure."""
        super().__init__(
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )
        self.registry = registry
        self.registry_error = registry_error

    @classmethod
    def from_files(
        cls,
        inventory_path: Path,
        platform_registry: PlatformRegistry | Path,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> "TurkeyInventoryTool":
        """Create a tool while retaining an explicit load error for its envelope."""
        try:
            registry = load_turkey_inventory_registry(inventory_path, platform_registry)
        except TurkeyInventoryRegistryError as error:
            return cls(
                None,
                event_id=event_id,
                request_id=request_id,
                event_service=event_service,
                registry_error=error,
            )
        return cls(
            registry,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )

    async def execute(
        self,
        request: TurkeyInventoryToolRequest,
        *,
        timeout_seconds: float,
    ) -> ToolResponseEnvelope[TurkeyInventoryResult]:
        """Map registry unavailability to an explicit ERROR plus UNKNOWN result."""
        if self.registry_error is None and self.registry is not None:
            return await super().execute(request, timeout_seconds=timeout_seconds)
        now = utc_now()
        data = self._unknown_result(request.platform_id, "INVENTORY_REGISTRY_UNAVAILABLE")
        envelope = ToolResponseEnvelope[TurkeyInventoryResult](
            tool_name=self.tool_name,
            tool_version=self.tool_version,
            event_id=self.event_id,
            request_id=self.request_id,
            execution_status=ToolExecutionStatus.ERROR,
            started_at_utc=now,
            finished_at_utc=utc_now(),
            latency_ms=0,
            data=data,
            warnings=["INVENTORY_REGISTRY_UNAVAILABLE"],
            error=ToolError(
                code="INVENTORY_REGISTRY_UNAVAILABLE",
                message="Turkey Inventory registry could not be loaded or validated",
                retryable=False,
            ),
        )
        await self._audit(
            request,
            envelope,
            attempt_number=1,
            domain_status=InventoryStatus.UNKNOWN.value,
        )
        return envelope

    async def execute_internal(
        self,
        request: TurkeyInventoryToolRequest,
    ) -> TurkeyInventoryResult:
        """Return exact domain status without alias or fuzzy matching."""
        if request.platform_status is PlatformStatus.NON_AIRCRAFT:
            raise ToolSkipped(
                self._not_applicable_result(request.platform_id),
                "NON_AIRCRAFT",
            )
        if (
            request.platform_execution_status is not ToolExecutionStatus.SUCCESS
            or request.platform_id is None
            or request.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}
        ):
            raise ToolSkipped(
                self._unknown_result(request.platform_id, "PLATFORM_NOT_RESOLVED"),
                "PLATFORM_NOT_RESOLVED",
            )

        assert self.registry is not None
        record = self.registry.find_active(request.platform_id)
        dataset = self.registry.dataset
        if record is None:
            return TurkeyInventoryResult(
                inventory_status=InventoryStatus.NOT_LISTED,
                platform_id=request.platform_id,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.dataset_version,
                source_type=dataset.source_type,
                reason_codes=["INVENTORY_NOT_LISTED"],
                safe_message=_NOT_LISTED_MESSAGE,
                warnings=[],
            )
        return TurkeyInventoryResult(
            inventory_status=InventoryStatus.CONFIRMED,
            platform_id=request.platform_id,
            inventory_record_id=record.inventory_record_id,
            country_code=record.country_code,
            operator_name=record.operator_name,
            service_status=record.service_status,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            source_type=record.source_type,
            reason_codes=["INVENTORY_SCOPE_CONFIRMED"],
            safe_message=_CONFIRMED_MESSAGE,
            warnings=["INVENTORY_CONFIRMATION_IS_NOT_FLIGHT_PERMISSION"],
        )

    def _unknown_result(
        self,
        platform_id: str | None,
        reason: str,
    ) -> TurkeyInventoryResult:
        return TurkeyInventoryResult(
            inventory_status=InventoryStatus.UNKNOWN,
            platform_id=platform_id or "UNRESOLVED",
            reason_codes=[reason],
            safe_message=_UNKNOWN_MESSAGE,
            warnings=[reason],
        )

    def _not_applicable_result(self, platform_id: str | None) -> TurkeyInventoryResult:
        return TurkeyInventoryResult(
            inventory_status=InventoryStatus.NOT_APPLICABLE,
            platform_id=platform_id or "NON_AIRCRAFT",
            reason_codes=["NON_AIRCRAFT"],
            safe_message=_NOT_APPLICABLE_MESSAGE,
            warnings=[],
        )

    @staticmethod
    def _source_refs(data: TurkeyInventoryResult) -> list[str]:
        if data.dataset_id is None or data.dataset_version is None:
            return []
        return [f"{data.dataset_id}@{data.dataset_version}"]

    @staticmethod
    def _domain_status(data: TurkeyInventoryResult) -> str:
        return data.inventory_status.value
