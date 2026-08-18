"""Shared real-DB Phase 7 orchestration test harness."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from operational_decision.app.demo_scenarios import build_demo_request
from operational_decision.context.context_repository import ContextRepository
from operational_decision.context.context_resolver import OperationalContextResolver
from operational_decision.contracts.common import DecisionCode, ToolExecutionStatus
from operational_decision.contracts.final_output import ModelVersions
from operational_decision.contracts.llm import LLMDecision
from operational_decision.contracts.permission import PermissionFlightPlanResult
from operational_decision.contracts.rag import RAGResult
from operational_decision.contracts.tools import ToolError, ToolResponseEnvelope
from operational_decision.decision.decision_policy import load_action_catalog
from operational_decision.decision.evidence_builder import EvidencePackageBuilder
from operational_decision.decision.operational_consistency_checker import (
    OperationalConsistencyChecker,
)
from operational_decision.decision.orchestrator import (
    DecisionOrchestrator,
    OrchestratorDependencies,
)
from operational_decision.decision.risk_advisor import RiskAdvisor
from operational_decision.decision.verification_checker import VerificationChecker
from operational_decision.finalizer.output_finalizer import OutputFinalizer
from operational_decision.inventory.turkey_inventory_registry import (
    load_turkey_inventory_registry,
)
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError
from operational_decision.llm.response_parser import StructuredDecisionRunner
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import EventService
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.operational.seed_loader import seed_operational_database
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)
from operational_decision.tools.notam_tool import NotamTool
from operational_decision.tools.permission_flight_plan_tool import PermissionFlightPlanTool
from operational_decision.tools.platform_tool import PlatformTool
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool


class FixedCounter:
    """Bounded deterministic evidence counter."""

    def encode(self, text: str) -> list[int]:
        """Return a stable small token sequence for orchestration tests."""
        return list(range(min(100, len(text))))


class EvidenceAwareLLM(BaseLLMClient):
    """Return the first allowed decision from the actual evidence package."""

    def __init__(
        self,
        outputs: list[str] | None = None,
        *,
        unload_fails: bool = False,
        generate_error: str | None = None,
        track_parallel: bool = False,
    ) -> None:
        """Configure optional malformed outputs and unload behavior."""
        self.outputs = list(outputs or [])
        self.unload_fails = unload_fails
        self.generate_error = generate_error
        self.generate_calls = 0
        self.unload_calls = 0
        self.last_evidence: dict[str, Any] | None = None

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a schema-valid draft or consume one scripted response."""
        self.generate_calls += 1
        if self.generate_error is not None:
            raise LocalLLMError(self.generate_error)
        if self.outputs:
            return self.outputs.pop(0)
        content = messages[1]["content"]
        evidence = json.loads(content[content.index("{") :])
        self.last_evidence = evidence
        code = evidence["constraints"]["allowed_decision_codes"][0]
        return LLMDecision(
            decision_code=DecisionCode(code),
            summary_tr="YapÄ±landÄ±rÄ±lmÄ±ÅŸ operasyonel kayÄ±tlar deÄŸerlendirilmiÅŸtir.",
        ).model_dump_json()

    async def unload(self) -> None:
        """Count explicit unload and optionally raise a controlled failure."""
        self.unload_calls += 1
        if self.unload_fails:
            raise LocalLLMError("stub unload failed")


class StubRAGTool:
    """Return an empty but successful policy-triggered RAG result."""

    def __init__(self, event_id: str, request_id: str, service: EventService) -> None:
        """Store audit identifiers."""
        self.event_id = event_id
        self.request_id = request_id
        self.service = service

    async def execute(
        self, request: Any, *, timeout_seconds: float
    ) -> ToolResponseEnvelope[RAGResult]:
        """Return success and write one normal tool execution record."""
        del timeout_seconds
        now = datetime.now(UTC)
        result = RAGResult(called=True, query_template_id=request.query_template_id)
        envelope = ToolResponseEnvelope[RAGResult](
            tool_name="text_rag",
            tool_version="1.0.0",
            event_id=self.event_id,
            request_id=self.request_id,
            execution_status=ToolExecutionStatus.SUCCESS,
            started_at_utc=now,
            finished_at_utc=now,
            latency_ms=0,
            data=result,
        )
        await self.service.record_tool_execution(
            event_id=self.event_id,
            request_id=self.request_id,
            tool_name="text_rag",
            attempt_number=1,
            execution_status="SUCCESS",
            domain_status="NO_CONTEXT",
            response=envelope.model_dump(mode="json"),
            latency_ms=0,
        )
        return envelope


class PermissionScenarioTool:
    """Inject only the binding SCN-07 permission infrastructure failure."""

    def __init__(
        self,
        actual: PermissionFlightPlanTool,
        event_id: str,
        request_id: str,
        service: EventService,
    ) -> None:
        """Wrap the real permission tool."""
        self.actual = actual
        self.event_id = event_id
        self.request_id = request_id
        self.service = service

    async def execute(
        self, request: Any, *, timeout_seconds: float
    ) -> ToolResponseEnvelope[PermissionFlightPlanResult]:
        """Delegate all scenarios except SCN-07 to the real repositories."""
        if request.scenario_id != "SCN-07":
            return await self.actual.execute(request, timeout_seconds=timeout_seconds)
        now = datetime.now(UTC)
        envelope = ToolResponseEnvelope[PermissionFlightPlanResult](
            tool_name="permission_flight_plan_tool",
            tool_version="1.0.0",
            event_id=self.event_id,
            request_id=self.request_id,
            execution_status=ToolExecutionStatus.ERROR,
            started_at_utc=now,
            finished_at_utc=now,
            latency_ms=0,
            error=ToolError(code="DEMO_TOOL_ERROR", message="controlled demo failure"),
        )
        await self.service.record_tool_execution(
            event_id=self.event_id,
            request_id=self.request_id,
            tool_name="permission_flight_plan_tool",
            attempt_number=1,
            execution_status="ERROR",
            error_code="DEMO_TOOL_ERROR",
            response=envelope.model_dump(mode="json"),
            latency_ms=0,
        )
        return envelope


class DelayedTool:
    """Record start/end ordering around a wrapped real tool."""

    def __init__(self, actual: Any, name: str, events: list[str], delay: float) -> None:
        self.actual = actual
        self.name = name
        self.events = events
        self.delay = delay

    async def execute(self, request: Any, *, timeout_seconds: float) -> Any:
        self.events.append(f"{self.name}:start")
        await asyncio.sleep(self.delay)
        result = await self.actual.execute(request, timeout_seconds=timeout_seconds)
        self.events.append(f"{self.name}:end")
        return result


@dataclass(slots=True)
class Phase7Harness:
    """Constructed orchestrator and inspectable dependencies."""

    orchestrator: DecisionOrchestrator
    event_service: EventService
    llm: EvidenceAwareLLM
    operational_db: OperationalDatabase
    parallel_events: list[str]


async def build_harness(
    root: Path,
    temp_dir: Path,
    *,
    outputs: list[str] | None = None,
    unload_fails: bool = False,
    track_parallel: bool = False,
    generate_error: str | None = None,
    llm_enabled: bool = True,
) -> Phase7Harness:
    """Build real migrated and seeded DBs with only RAG/Ollama stubbed."""
    operational_db = OperationalDatabase(temp_dir / "operational.db")
    event_db = EventMemoryDatabase(temp_dir / "event_memory.db")
    await operational_db.initialize()
    await event_db.initialize()
    await seed_operational_database(operational_db, root / "data/seeds")
    service = EventService(event_db)
    registry = PlatformRegistryIndex(
        load_platform_registry(root / "data/platforms/platform_registry.json"),
        load_platform_aliases(root / "data/platforms/platform_aliases.json"),
    )
    inventory_registry = load_turkey_inventory_registry(
        root / "data/inventory/turkey_inventory.json",
        root / "data/platforms/platform_registry.json",
    )
    permission_repository = PermissionRepository(operational_db)
    flight_repository = FlightPlanRepository(operational_db)
    notam_repository = NotamRepository(operational_db)
    llm = EvidenceAwareLLM(
        outputs,
        unload_fails=unload_fails,
        generate_error=generate_error,
    )
    parallel_events: list[str] = []

    def platform_factory(event_id: str, request_id: str) -> Any:
        tool = PlatformTool(
            registry,
            event_id=event_id,
            request_id=request_id,
            event_service=service,
        )
        return DelayedTool(tool, "platform", parallel_events, 0.05) if track_parallel else tool

    def inventory_factory(event_id: str, request_id: str) -> TurkeyInventoryTool:
        return TurkeyInventoryTool(
            inventory_registry, event_id=event_id, request_id=request_id, event_service=service
        )

    def permission_factory(event_id: str, request_id: str) -> PermissionScenarioTool:
        actual = PermissionFlightPlanTool(
            permission_repository,
            flight_repository,
            event_id=event_id,
            request_id=request_id,
            event_service=service,
        )
        return PermissionScenarioTool(actual, event_id, request_id, service)

    def notam_factory(event_id: str, request_id: str) -> Any:
        tool = NotamTool(
            notam_repository,
            event_id=event_id,
            request_id=request_id,
            event_service=service,
        )
        return DelayedTool(tool, "notam", parallel_events, 0.05) if track_parallel else tool

    dependencies = OrchestratorDependencies(
        event_service=service,
        context_resolver=OperationalContextResolver(ContextRepository(operational_db)),
        platform_factory=platform_factory,
        inventory_factory=inventory_factory,
        permission_factory=permission_factory,
        notam_factory=notam_factory,
        rag_factory=lambda event_id, request_id: StubRAGTool(event_id, request_id, service),
        consistency_checker=OperationalConsistencyChecker(),
        verification_checker=VerificationChecker(),
        risk_advisor=RiskAdvisor.from_yaml(root / "data/rules/risk_rules.yaml"),
        evidence_builder=EvidencePackageBuilder(FixedCounter()),
        decision_runner=StructuredDecisionRunner(llm),
        llm_client=llm,
        output_finalizer=OutputFinalizer(),
        action_catalog=load_action_catalog(root / "data/rules/action_catalog.yaml"),
        model_versions=ModelVersions(decision_llm="stub-phase7"),
        llm_enabled=llm_enabled,
    )
    return Phase7Harness(
        DecisionOrchestrator(dependencies), service, llm, operational_db, parallel_events
    )


def scenario_payload(root: Path, scenario_number: int, *, released: bool = True) -> dict[str, Any]:
    """Build one request through the production demo payload source."""
    request = build_demo_request(
        root,
        f"SCN-{scenario_number:02d}",
        released=released,
    )
    return request.model_dump(mode="json")
