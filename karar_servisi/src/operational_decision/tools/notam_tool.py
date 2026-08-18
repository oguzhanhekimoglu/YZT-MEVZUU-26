"""Metadata-only NOTAM relevance and strongest-effect selection."""

from collections.abc import Mapping
from typing import Any

from operational_decision.contracts.common import (
    ContextStatus,
    NotamOperationEffect,
    NotamStatus,
    VisualClass,
)
from operational_decision.contracts.notam import NotamRecord, NotamResult, NotamToolRequest
from operational_decision.memory.event_service import EventService
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.tools.base import BaseTool, ToolSkipped

_EFFECT_PRECEDENCE = {
    NotamOperationEffect.NO_EFFECT: 0,
    NotamOperationEffect.INFORMATIONAL: 1,
    NotamOperationEffect.REQUIRES_ADDITIONAL_CHECK: 2,
    NotamOperationEffect.RESTRICTS_OPERATION: 3,
    NotamOperationEffect.CONFLICTS_WITH_PERMISSION: 4,
    NotamOperationEffect.PROHIBITS_OPERATION: 5,
    NotamOperationEffect.UNKNOWN: -1,
}


def _record(row: Mapping[str, Any]) -> NotamRecord:
    return NotamRecord(
        notam_id=row["notam_id"],
        operational_area_id=row["operational_area_id"],
        valid_from_utc=row["valid_from_utc"],
        valid_to_utc=row["valid_to_utc"],
        notam_status=NotamStatus(row["notam_status"]),
        operation_effect=NotamOperationEffect(row["operation_effect"]),
        display_number=row.get("display_number"),
        series=row.get("series"),
        number=row.get("number"),
        year=row.get("year"),
        q_code=row.get("q_code"),
        item_e=row.get("item_e"),
        estimated_end=bool(row.get("estimated_end", False)),
        permanent=bool(row.get("permanent", False)),
        lower_limit=row.get("lower_limit"),
        upper_limit=row.get("upper_limit"),
        fir_code=row.get("fir_code"),
        aerodrome_code=row.get("aerodrome_code"),
        operational_reason_tr=row.get("operational_reason_tr"),
        conflict_with_permission=bool(row.get("conflict_with_permission", False)),
        conflict_with_flight_plan=bool(row.get("conflict_with_flight_plan", False)),
        context_id=row["context_id"],
        scenario_id=row["scenario_id"],
        relevance_tags=row["relevance_tags"],
        affected_platform_categories=[
            VisualClass(value) for value in row["affected_platform_categories"]
        ],
        affected_platform_ids=row["affected_platform_ids"],
        summary_tr=row["summary_tr"],
        source_reference=row["source_reference"],
        source_type=row["source_type"],
    )


def _metadata_match(row: Mapping[str, Any], request: NotamToolRequest) -> tuple[bool, list[str]]:
    """Return deterministic relevance plus the exact facts that matched."""
    matched_by = ["TIME_OVERLAP"]
    if row["operational_area_id"] != request.operational_area_id:
        return False, []
    matched_by.append("AREA_MATCH")
    if row.get("fir_code") is not None and request.fir_code is not None:
        if row["fir_code"] != request.fir_code:
            return False, []
        matched_by.append("FIR_MATCH")
    if row.get("aerodrome_code") is not None and request.aerodrome_code is not None:
        if row["aerodrome_code"] != request.aerodrome_code:
            return False, []
        matched_by.append("AERODROME_MATCH")
    if row["context_id"] is not None:
        if row["context_id"] != request.context_id:
            return False, []
        matched_by.append("CONTEXT_MATCH")
    if row["scenario_id"] is not None:
        if row["scenario_id"] != request.scenario_id:
            return False, []
        matched_by.append("SCENARIO_MATCH")
    categories = set(row["affected_platform_categories"])
    if categories:
        if request.visual_class.value not in categories:
            return False, []
        matched_by.append("PLATFORM_CATEGORY_MATCH")
    platform_ids = set(row["affected_platform_ids"])
    if platform_ids and request.platform_id is not None:
        if request.platform_id not in platform_ids:
            return False, []
        matched_by.append("PLATFORM_MATCH")
    record_tags = set(row["relevance_tags"])
    request_tags = set(request.relevance_tags)
    if record_tags and request_tags:
        if record_tags.isdisjoint(request_tags):
            return False, []
        matched_by.append("OPERATION_TAG_MATCH")
    lower = row.get("lower_limit")
    upper = row.get("upper_limit")
    request_lower = request.operation_lower_limit
    request_upper = request.operation_upper_limit
    if lower is not None and upper is not None:
        if request_lower is None or request_upper is None:
            return False, []
        if upper < request_lower or lower > request_upper:
            return False, []
        matched_by.append("ALTITUDE_OVERLAP")
    return True, matched_by


def _strongest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: _EFFECT_PRECEDENCE[NotamOperationEffect(row["operation_effect"])],
    )


class NotamTool(BaseTool[NotamToolRequest, NotamResult]):
    """Query local NOTAMs and calculate relevance only from operational facts."""

    tool_name = "notam_tool"

    def __init__(
        self,
        repository: NotamRepository,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> None:
        """Bind the NOTAM repository."""
        super().__init__(event_id=event_id, request_id=request_id, event_service=event_service)
        self.repository = repository

    def validate_request(self, request: NotamToolRequest) -> None:
        """Reject inverted observation and altitude intervals."""
        if request.observation_end_time_utc < request.observation_time_utc:
            raise ValueError("observation interval is inverted")
        if (
            request.operation_lower_limit is not None
            and request.operation_upper_limit is not None
            and request.operation_upper_limit < request.operation_lower_limit
        ):
            raise ValueError("operation altitude interval is inverted")

    async def execute_internal(self, request: NotamToolRequest) -> NotamResult:
        """Select temporal state, metadata relevance, conflict, and effect."""
        if request.context_status is not ContextStatus.COMPLETE:
            data = NotamResult(
                notam_status=NotamStatus.NONE_ACTIVE,
                operation_effect=NotamOperationEffect.NO_EFFECT,
                skip_reason="CONTEXT_NOT_COMPLETE",
            )
            raise ToolSkipped(data, "CONTEXT_NOT_COMPLETE")
        if (
            request.context_id is None
            or request.operational_area_id is None
            or request.scenario_id is None
        ):
            raise ValueError("complete context requires context, area, and scenario identifiers")

        rows = await self.repository.find_by_area(request.operational_area_id)
        active = [
            row
            for row in rows
            if row["valid_from_utc"] <= request.observation_end_time_utc
            and row["valid_to_utc"] >= request.observation_time_utc
        ]
        if not active:
            relevant_rows = [row for row in rows if _metadata_match(row, request)[0]]
            past = [
                row for row in relevant_rows if row["valid_to_utc"] < request.observation_time_utc
            ]
            future = [
                row
                for row in relevant_rows
                if row["valid_from_utc"] > request.observation_end_time_utc
            ]
            if past and not future:
                status = NotamStatus.EXPIRED_ONLY
            elif future and not past:
                status = NotamStatus.NOT_YET_ACTIVE
            else:
                status = NotamStatus.NONE_ACTIVE
            return NotamResult(notam_status=status, operation_effect=NotamOperationEffect.NO_EFFECT)

        matches = [
            (row, reasons)
            for row in active
            if (result := _metadata_match(row, request))[0]
            for reasons in [result[1]]
        ]
        if not matches:
            return NotamResult(
                notam_status=NotamStatus.ACTIVE_NOT_RELEVANT,
                operation_effect=NotamOperationEffect.NO_EFFECT,
                active_notams=[_record(row) for row in active],
            )

        relevant = [row for row, _ in matches]
        primary = _strongest_row(relevant)
        matched_by = list(dict.fromkeys(reason for _, reasons in matches for reason in reasons))
        conflict_permission = any(bool(row.get("conflict_with_permission")) for row in relevant)
        conflict_plan = any(bool(row.get("conflict_with_flight_plan")) for row in relevant)
        conflict = any(
            NotamStatus(row["notam_status"]) is NotamStatus.CONFLICTING for row in relevant
        )
        return NotamResult(
            notam_status=NotamStatus.CONFLICTING if conflict else NotamStatus.ACTIVE_RELEVANT,
            operation_effect=NotamOperationEffect(primary["operation_effect"]),
            active_notams=[_record(row) for row in relevant],
            matched_notam_ids=[row["notam_id"] for row in relevant],
            primary_notam_number=primary.get("display_number"),
            reason_tr=primary.get("operational_reason_tr") or primary["summary_tr"],
            matched_by=matched_by,
            conflict_with_permission=conflict_permission,
            conflict_with_flight_plan=conflict_plan,
        )
