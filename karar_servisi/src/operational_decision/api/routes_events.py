"""Event, trace, demo, and RAG status HTTP adapters."""

import json
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from operational_decision.api.dependencies import get_container
from operational_decision.api.schemas import AnalyzeResponse, DemoScenarioResponse
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.demo_scenarios import (
    build_demo_request,
    load_demo_scenario_definitions,
)
from operational_decision.contracts.common import EventStatus
from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.request import AnalyzeEventRequest
from operational_decision.memory.event_service import EventNotFoundError
from operational_decision.presentation.teknofest import TeknofestSpecFormatter

router = APIRouter()


@router.post("/api/v1/events/analyze")
async def analyze_event(
    payload: Annotated[Any, Body()],
    container: Annotated[ApplicationContainer, Depends(get_container)],
    response_format: Annotated[
        Literal["canonical", "teknofest_spec"], Query()
    ] = "canonical",
) -> JSONResponse:
    """Delegate one raw payload to the transport-neutral orchestrator."""
    outcome = await container.orchestrator.analyze(payload)
    if (
        response_format == "teknofest_spec"
        and outcome.http_status == 200
        and outcome.event_status == EventStatus.FINALIZED
    ):
        persisted = await container.event_service.get_final_output(outcome.event_id)
        if persisted is None or not isinstance(persisted.get("output"), dict):
            raise HTTPException(status_code=500, detail="FINAL_OUTPUT_NOT_PERSISTED")
        canonical = FinalDecisionOutput.model_validate_json(
            json.dumps(persisted["output"], ensure_ascii=False),
            strict=True,
        )
        request = AnalyzeEventRequest.model_validate_json(
            json.dumps(payload, ensure_ascii=False),
            strict=True,
        )
        formatted = TeknofestSpecFormatter(
            container.orchestrator.deps.action_catalog
        ).format(
            canonical,
            first_seen_offset_seconds=request.visual_evidence.timing.first_seen_offset_seconds,
        )
        return JSONResponse(status_code=200, content=formatted.model_dump(mode="json"))
    response = AnalyzeResponse(
        event_id=outcome.event_id,
        request_id=outcome.request_id,
        event_status=outcome.event_status,
        output=outcome.output,
        detail=outcome.detail,
    )
    return JSONResponse(
        status_code=outcome.http_status,
        content=response.model_dump(mode="json"),
    )


@router.get("/api/v1/events/{event_id}")
async def get_event(
    event_id: str,
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> dict[str, Any]:
    """Return one event and its persisted final output when available."""
    event = await container.event_service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")
    final_output = await container.event_service.get_final_output(event_id)
    return cast(dict[str, Any], jsonable_encoder({"event": event, "final_output": final_output}))


@router.get("/api/v1/events/{event_id}/trace")
async def get_event_trace(
    event_id: str,
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> dict[str, Any]:
    """Return ordered lifecycle, tool, raw-audit, and final-output records."""
    try:
        trace = await container.event_service.get_event_trace(event_id)
    except EventNotFoundError as error:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND") from error
    return cast(dict[str, Any], jsonable_encoder(trace))


@router.get("/api/v1/demo/scenarios")
async def get_demo_scenarios(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> list[DemoScenarioResponse]:
    """Return runnable canonical requests for the deterministic demo catalog."""
    if container.runtime_mode != "DEMO":
        raise HTTPException(status_code=404, detail="DEMO_ENDPOINT_DISABLED")
    try:
        definitions = load_demo_scenario_definitions(container.scenario_path)
        project_root = container.scenario_path.resolve().parents[2]
        return [
            DemoScenarioResponse(
                **definition.model_dump(),
                request_payload=build_demo_request(project_root, definition.scenario_id),
            )
            for definition in definitions
        ]
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail="SCENARIO_CATALOG_INVALID") from error


@router.get("/api/v1/rag/status")
async def get_rag_status(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> dict[str, Any]:
    """Expose RAG health without performing retrieval or generation."""
    report = await container.health_service.check(deep=False)
    return {
        "rag_index": report.components.get("rag_index"),
        "embedding_model": report.components.get("embedding_model"),
    }
