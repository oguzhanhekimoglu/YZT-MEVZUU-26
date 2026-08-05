"""End-to-end deterministic decision orchestration independent of FastAPI."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from operational_decision.context.context_resolver import OperationalContextResolver
from operational_decision.contracts.common import (
    ContextStatus,
    DecisionCode,
    EventStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    ToolExecutionStatus,
)
from operational_decision.contracts.context import ContextResolution
from operational_decision.contracts.final_output import (
    FinalDecisionOutput,
    ModelVersions,
    ToolExecutionSummaryItem,
)
from operational_decision.contracts.inventory import (
    TurkeyInventoryResult,
    TurkeyInventoryToolRequest,
)
from operational_decision.contracts.llm import EvidenceConstraints, LLMDecision
from operational_decision.contracts.notam import NotamResult, NotamToolRequest
from operational_decision.contracts.operational_consistency import (
    OperationalConsistencyInput,
    OperationalConsistencyResult,
)
from operational_decision.contracts.permission import (
    PermissionFlightPlanRequest,
    PermissionFlightPlanResult,
)
from operational_decision.contracts.platform import PlatformResult, PlatformToolRequest
from operational_decision.contracts.rag import RAGResult, TextRAGRequest
from operational_decision.contracts.request import AnalyzeEventRequest
from operational_decision.contracts.risk import ActionCatalog, RiskResult
from operational_decision.contracts.tools import ToolResponseEnvelope
from operational_decision.contracts.verification import (
    VerificationInput,
    VerificationResult,
)
from operational_decision.decision.decision_policy import (
    allowed_action_codes,
    allowed_decision_codes,
)
from operational_decision.decision.evidence_builder import EvidencePackageBuilder
from operational_decision.decision.gpu_handoff import BatchCoordinator, GPUHandoffGate
from operational_decision.decision.operational_consistency_checker import (
    OperationalConsistencyChecker,
)
from operational_decision.decision.rag_policy import select_text_rag_query, should_call_text_rag
from operational_decision.decision.risk_advisor import RiskAdvisor
from operational_decision.decision.verification_checker import (
    VerificationChecker,
    is_unregistered_military_policy,
    should_early_exit_non_aircraft,
)
from operational_decision.decision.vlm_origin import classify_vlm_origin
from operational_decision.finalizer.output_finalizer import FinalizationMetadata, OutputFinalizer
from operational_decision.finalizer.turkish_report import refresh_final_presentation
from operational_decision.llm.base_client import BaseLLMClient
from operational_decision.llm.response_parser import StructuredDecisionRunner
from operational_decision.memory.event_service import (
    DuplicateProcessingError,
    EventCreationKind,
    EventService,
    generate_event_fingerprint,
)
from operational_decision.observability.logger import EventLogger
from operational_decision.observability.metrics import MetricsRegistry
from operational_decision.observability.timers import OperationTimer
from operational_decision.persistence.sqlite_database import utc_now

DataT = TypeVar("DataT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class OrchestratorDependencies:
    """Explicit Phase 1ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“6 services used by core orchestration."""

    event_service: EventService
    context_resolver: OperationalContextResolver
    platform_factory: Callable[[str, str], Any]
    inventory_factory: Callable[[str, str], Any]
    permission_factory: Callable[[str, str], Any]
    notam_factory: Callable[[str, str], Any]
    rag_factory: Callable[[str, str], Any] | None
    consistency_checker: OperationalConsistencyChecker
    verification_checker: VerificationChecker
    risk_advisor: RiskAdvisor
    evidence_builder: EvidencePackageBuilder
    decision_runner: StructuredDecisionRunner
    llm_client: BaseLLMClient
    output_finalizer: OutputFinalizer
    action_catalog: ActionCatalog
    model_versions: ModelVersions
    llm_enabled: bool = True


@dataclass(frozen=True, slots=True)
class AnalyzeOutcome:
    """Transport-neutral orchestration response."""

    http_status: int
    event_id: str
    request_id: str
    event_status: EventStatus
    output: dict[str, Any] | None = None
    detail: str | None = None


class DecisionOrchestrator:
    """Connect deterministic tools, risk, conditional RAG, LLM, and persistence."""

    def __init__(
        self,
        dependencies: OrchestratorDependencies,
        *,
        gpu_gate: GPUHandoffGate | None = None,
        coordinator: BatchCoordinator | None = None,
        metrics: MetricsRegistry | None = None,
        logger: EventLogger | None = None,
        non_aircraft_threshold: float = 0.85,
    ) -> None:
        """Configure orchestration without constructing infrastructure in core logic."""
        self.deps = dependencies
        self.gpu_gate = gpu_gate or GPUHandoffGate()
        self.coordinator = coordinator or BatchCoordinator()
        self.metrics = metrics or MetricsRegistry()
        self.logger = logger or EventLogger()
        self.non_aircraft_threshold = non_aircraft_threshold

    async def analyze(self, raw_payload: object) -> AnalyzeOutcome:
        """Analyze one payload, auditing invalid input and preserving idempotency."""
        timer = OperationTimer()
        try:
            request = AnalyzeEventRequest.model_validate_json(
                json.dumps(raw_payload, ensure_ascii=False), strict=True
            )
        except (TypeError, ValueError, ValidationError) as error:
            return await self._reject_invalid(raw_payload, error)
        async with self.coordinator.video_batch(request.video_id):
            outcome = await self._analyze_serial(request, raw_payload)
        self.metrics.observe_ms("total_event_latency_ms", timer.elapsed_ms())
        return outcome

    async def _reject_invalid(self, raw_payload: object, error: Exception) -> AnalyzeOutcome:
        created = await self.deps.event_service.create_event(raw_request=raw_payload)
        event_id = str(created.event["event_id"])
        request_id = str(created.event["request_id"])
        await self.deps.event_service.record_event_step(
            event_id,
            "CANONICAL_INPUT_VALIDATION",
            "INVALID",
            {"error_count": (error.error_count() if isinstance(error, ValidationError) else 1)},
        )
        await self.deps.event_service.reject_invalid_input(event_id, "INVALID_INPUT")
        output = FinalDecisionOutput(
            event_id=event_id,
            request_id=request_id,
            event_status=EventStatus.REJECTED_INVALID_INPUT,
            decision=DecisionCode.INDETERMINATE,
            risk_level=RiskLevel.UNKNOWN,
            minimum_risk_level=RiskLevel.UNKNOWN,
            summary_tr=(
                "Girdi sozlesme dogrulamasindan gecemedi; olay operator incelemesine ayrildi."
            ),
            human_approval_required=True,
            uncertainty_notes=["INVALID_INPUT"],
        )
        await self.deps.event_service.store_final_output(
            event_id, output.schema_version, output.model_dump(mode="json")
        )
        self.metrics.increment("invalid_input_rate")
        return AnalyzeOutcome(
            422,
            event_id,
            request_id,
            EventStatus.REJECTED_INVALID_INPUT,
            output.model_dump(mode="json"),
            "INVALID_INPUT",
        )

    async def _analyze_serial(
        self, request: AnalyzeEventRequest, raw_payload: object
    ) -> AnalyzeOutcome:
        visual = request.visual_evidence
        fingerprint = generate_event_fingerprint(
            request.video_id, visual.track_id, visual.timing.first_seen_offset_seconds
        )
        active = await self.deps.event_service.get_active_by_fingerprint(fingerprint)
        resumed = (
            active is not None and active["event_status"] is EventStatus.WAITING_FOR_GPU_HANDOFF
        )
        if active is not None and not resumed:
            raise DuplicateProcessingError(str(active["event_id"]))
        event: dict[str, Any]
        if resumed:
            assert active is not None
            event = active
            await self.deps.event_service.record_event_step(
                str(event["event_id"]), "GPU_HANDOFF_RESUME", "REQUESTED"
            )
        else:
            created = await self.deps.event_service.create_event(
                raw_request=raw_payload,
                fingerprint=fingerprint,
                video_id=request.video_id,
                track_id=visual.track_id,
            )
            if created.kind is EventCreationKind.FINALIZED_DUPLICATE:
                final_row = created.final_output or {}
                persisted_output = final_row.get("output")
                output = persisted_output
                if (
                    isinstance(persisted_output, dict)
                    and persisted_output.get("schema_version") == "final-output/2.1"
                ):
                    refreshed = refresh_final_presentation(persisted_output)
                    if refreshed != persisted_output:
                        await self.deps.event_service.store_final_output(
                            str(created.event["event_id"]),
                            "final-output/2.1",
                            refreshed,
                        )
                        await self.deps.event_service.record_event_step(
                            str(created.event["event_id"]),
                            "FINAL_PRESENTATION_REFRESH",
                            "SUCCESS",
                            {"reason": "STALE_DERIVED_PRESENTATION"},
                        )
                    output = refreshed
                return AnalyzeOutcome(
                    200,
                    str(created.event["event_id"]),
                    str(created.event["request_id"]),
                    EventStatus.FINALIZED,
                    output,
                )
            event = created.event
            await self.deps.event_service.update_event_status(
                str(event["event_id"]), EventStatus.INPUT_VALIDATED
            )
        event_id, request_id = str(event["event_id"]), str(event["request_id"])
        context = await self.deps.context_resolver.resolve_context(
            request.video_id,
            visual.timing.first_seen_offset_seconds,
            visual.timing.last_seen_offset_seconds,
        )
        await self.deps.event_service.record_event_step(
            event_id,
            "CONTEXT_RESOLUTION",
            context.context_status.value,
            context.model_dump(mode="json"),
        )
        if not resumed:
            await self.deps.event_service.update_event_status(
                event_id, EventStatus.CONTEXT_RESOLVED
            )
        if not self.gpu_gate.is_released(request.gpu_handoff):
            if not resumed:
                await self.deps.event_service.update_event_status(
                    event_id, EventStatus.WAITING_FOR_GPU_HANDOFF
                )
            self.metrics.increment("gpu_waiting_rate")
            return AnalyzeOutcome(
                202,
                event_id,
                request_id,
                EventStatus.WAITING_FOR_GPU_HANDOFF,
                detail="WAITING_FOR_GPU_HANDOFF",
            )
        await self.deps.event_service.update_event_status(event_id, EventStatus.TOOLS_RUNNING)
        try:
            return await self._run_pipeline(request, context, event_id, request_id)
        except Exception as error:
            await self.deps.event_service.mark_event_failed(
                event_id, "ORCHESTRATOR_ERROR", type(error).__name__
            )
            self.metrics.increment("event_failure_rate")
            raise

    async def _run_pipeline(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        event_id: str,
        request_id: str,
    ) -> AnalyzeOutcome:
        visual = request.visual_evidence
        early = should_early_exit_non_aircraft(visual, self.non_aircraft_threshold)
        if early:
            self.metrics.increment("early_exit_rate")
            platform_env = await self._manual(
                event_id,
                request_id,
                "platform_tool",
                PlatformResult(platform_status=PlatformStatus.NON_AIRCRAFT),
                "STRONG_NON_AIRCRAFT",
            )
        else:
            platform_env = await self._platform_tool_only(request, context, event_id, request_id)

        platform_data = platform_env.data or PlatformResult(platform_status=PlatformStatus.UNKNOWN)
        inventory_env = cast(
            ToolResponseEnvelope[TurkeyInventoryResult],
            await self.deps.inventory_factory(event_id, request_id).execute(
                TurkeyInventoryToolRequest(
                    platform_id=platform_data.platform_id,
                    platform_execution_status=platform_env.execution_status,
                    platform_status=platform_data.platform_status,
                ),
                timeout_seconds=0.2,
            ),
        )
        record = context.record
        platform_resolved = (
            platform_env.execution_status is ToolExecutionStatus.SUCCESS
            and platform_data.platform_id is not None
            and platform_data.platform_status
            in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        )
        context_complete = (
            context.context_status is ContextStatus.COMPLETE
            and record is not None
            and record.context_id is not None
            and record.operational_area_id is not None
            and record.scenario_id is not None
            and context.observation_time_utc is not None
            and context.observation_end_time_utc is not None
        )
        policy_skips_downstream = (
            inventory_env.data is not None
            and is_unregistered_military_policy(
                platform_usage_domain=platform_data.usage_domain,
                inventory_execution_status=inventory_env.execution_status,
                inventory_status=inventory_env.data.inventory_status,
            )
        )
        if platform_resolved and context_complete:
            if policy_skips_downstream:
                skip_reason = "UNREGISTERED_MILITARY_POLICY"
                permission_env = await self._empty_permission_skip(
                    event_id, request_id, skip_reason
                )
                notam_env = await self._empty_notam_skip(event_id, request_id, skip_reason)
            else:
                permission_env, notam_env = await self._eligible_downstream_tools(
                    request,
                    context,
                    platform_env,
                    event_id,
                    request_id,
                )
        else:
            skip_reason = "CONTEXT_INCOMPLETE" if not context_complete else "PLATFORM_UNRESOLVED"
            permission_env = await self._empty_permission_skip(event_id, request_id, skip_reason)
            notam_env = await self._empty_notam_skip(event_id, request_id, skip_reason)

        consistency = self.deps.consistency_checker.check(
            OperationalConsistencyInput(
                context=context,
                platform=platform_env.data,
                inventory=inventory_env.data,
                permission_flight_plan=permission_env.data,
                notam=notam_env.data,
                visual_evidence=visual,
                platform_execution_status=platform_env.execution_status,
                inventory_execution_status=inventory_env.execution_status,
                permission_execution_status=permission_env.execution_status,
                notam_execution_status=notam_env.execution_status,
            )
        )
        await self.deps.event_service.record_event_step(
            event_id,
            "OPERATIONAL_CONSISTENCY",
            consistency.status.value,
            consistency.model_dump(mode="json"),
        )
        facts = self._facts(
            request,
            context,
            platform_env,
            inventory_env,
            permission_env,
            notam_env,
            consistency,
        )
        await self.deps.event_service.update_event_status(event_id, EventStatus.TOOLS_COMPLETED)
        verification = self.deps.verification_checker.check(facts, strong_non_aircraft=early)
        await self.deps.event_service.record_event_step(
            event_id,
            "VERIFICATION",
            verification.verification_status.value,
            verification.model_dump(mode="json"),
        )
        await self.deps.event_service.update_event_status(
            event_id, EventStatus.VERIFICATION_COMPLETED
        )
        risk = self.deps.risk_advisor.assess(facts, verification)
        await self.deps.event_service.record_event_step(
            event_id, "RISK", risk.risk_level.value, risk.model_dump(mode="json")
        )
        await self.deps.event_service.update_event_status(event_id, EventStatus.RISK_ASSESSED)
        return await self._post_risk(
            request,
            context,
            event_id,
            request_id,
            platform_env,
            inventory_env,
            permission_env,
            notam_env,
            consistency,
            facts,
            verification,
            risk,
            early,
        )

    async def _post_risk(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        event_id: str,
        request_id: str,
        platform_env: ToolResponseEnvelope[PlatformResult],
        inventory_env: ToolResponseEnvelope[TurkeyInventoryResult],
        permission_env: ToolResponseEnvelope[PermissionFlightPlanResult],
        notam_env: ToolResponseEnvelope[NotamResult],
        consistency: OperationalConsistencyResult,
        facts: VerificationInput,
        verification: VerificationResult,
        risk: RiskResult,
        early: bool,
    ) -> AnalyzeOutcome:
        rag, rag_called = RAGResult(called=False), False
        if not early and should_call_text_rag(
            verification_status=verification.verification_status,
            risk_level=risk.risk_level,
            tool_health_status=verification.tool_health_status,
            facts=facts,
            explanation_requested=request.explanation_requested,
        ):
            plan = select_text_rag_query(facts)
            if plan is not None and self.deps.rag_factory is not None:
                rag_called = True
                envelope = await self.deps.rag_factory(event_id, request_id).execute(
                    TextRAGRequest(
                        query_template_id=plan.query_template_id,
                        query=plan.query,
                        document_ids=list(plan.document_ids),
                    ),
                    timeout_seconds=5.0,
                )
                rag = envelope.data or RAGResult(
                    called=True,
                    warnings=[envelope.error.code if envelope.error else "RAG_FAILED"],
                )
                self.metrics.increment("rag_call_rate")
                await self.deps.event_service.update_event_status(
                    event_id, EventStatus.RAG_COMPLETED
                )
            else:
                rag = RAGResult(called=False, warnings=["NO_DEFINED_QUERY_TEMPLATE"])
        await self.deps.event_service.record_event_step(
            event_id,
            "TEXT_RAG",
            "CALLED" if rag_called else "SKIPPED",
            rag.model_dump(mode="json"),
        )
        platform = platform_env.data or PlatformResult(platform_status=PlatformStatus.UNKNOWN)
        inventory = inventory_env.data or TurkeyInventoryResult(
            inventory_status=InventoryStatus.UNKNOWN,
            platform_id="UNRESOLVED",
            reason_codes=["INVENTORY_RESULT_UNAVAILABLE"],
            safe_message="Türkiye envanter sonucu kullanılamıyor.",
            warnings=["INVENTORY_RESULT_UNAVAILABLE"],
        )
        permission = permission_env.data or PermissionFlightPlanResult(
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
        )
        notam = notam_env.data or NotamResult(
            notam_status=NotamStatus.NONE_ACTIVE,
            operation_effect=NotamOperationEffect.UNKNOWN,
        )
        constraints = self._constraints(facts, verification, risk, rag)
        summaries = self._summaries(platform_env, permission_env, notam_env)
        summaries[inventory_env.tool_name] = ToolExecutionSummaryItem(
            execution_status=inventory_env.execution_status,
            latency_ms=inventory_env.latency_ms,
            domain_status=inventory.inventory_status.value,
            error_code=inventory_env.error.code if inventory_env.error else None,
            warnings=inventory_env.warnings,
        )
        if early:
            await self.deps.event_service.record_event_step(
                event_id, "LOCAL_LLM", "SKIPPED_STRONG_NON_AIRCRAFT"
            )
            return await self._finalize(
                request,
                context,
                event_id,
                request_id,
                platform,
                permission,
                notam,
                inventory,
                consistency,
                facts,
                verification,
                risk,
                rag,
                constraints,
                summaries,
                LLMDecision(
                    decision_code=DecisionCode.NON_AIRCRAFT,
                    summary_tr=(
                        "Guclu gorsel kanit hedefin hava araci olmadigini desteklemektedir."
                    ),
                ),
                None,
                False,
            )
        try:
            evidence = self.deps.evidence_builder.build(
                event_id=event_id,
                track_id=request.visual_evidence.track_id,
                observation_time_utc=context.observation_time_utc,
                visual_evidence=request.visual_evidence,
                operational_context=context,
                platform_result=platform,
                inventory_result=inventory,
                permission_flight_plan_result=permission,
                notam_result=notam,
                operational_consistency=consistency,
                verification=verification,
                facts=facts,
                risk=risk,
                rag=rag,
                action_catalog=self.deps.action_catalog,
            )
        except ValueError as error:
            await self.deps.event_service.record_event_step(
                event_id,
                "LOCAL_LLM",
                "SKIPPED_EVIDENCE_ERROR",
                {"error_codes": [type(error).__name__]},
            )
            return await self._finalize(
                request,
                context,
                event_id,
                request_id,
                platform,
                permission,
                notam,
                inventory,
                consistency,
                facts,
                verification,
                risk,
                rag,
                constraints,
                summaries,
                None,
                [type(error).__name__],
                False,
            )
        if not self.deps.llm_enabled:
            await self.deps.event_service.record_event_step(
                event_id,
                "LOCAL_LLM",
                "DISABLED_FALLBACK",
                {"error_codes": ["LOCAL_LLM_DISABLED"]},
            )
            return await self._finalize(
                request,
                context,
                event_id,
                request_id,
                platform,
                permission,
                notam,
                inventory,
                consistency,
                facts,
                verification,
                risk,
                rag,
                constraints,
                summaries,
                None,
                ["LOCAL_LLM_DISABLED"],
                False,
            )
        async with self.coordinator.llm_inference():
            timer = OperationTimer()
            run = await self.deps.decision_runner.run(evidence)
            self.metrics.observe_ms("llm_inference_latency_ms", timer.elapsed_ms())
            if run.repair_attempted:
                self.metrics.increment("llm_repair_rate")
            if run.fallback_required:
                self.metrics.increment("safe_fallback_rate")
            llm_status = (
                "FALLBACK"
                if run.fallback_required
                else "REPAIRED"
                if run.repair_attempted
                else "SUCCESS"
            )
            await self.deps.event_service.record_event_step(
                event_id,
                "LOCAL_LLM",
                llm_status,
                {"error_codes": run.errors},
            )
            return await self._finalize(
                request,
                context,
                event_id,
                request_id,
                platform,
                permission,
                notam,
                inventory,
                consistency,
                facts,
                verification,
                risk,
                rag,
                constraints,
                summaries,
                run.decision,
                run.errors or None,
                True,
            )

    async def _finalize(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        event_id: str,
        request_id: str,
        platform: PlatformResult,
        permission: PermissionFlightPlanResult,
        notam: NotamResult,
        inventory: TurkeyInventoryResult,
        consistency: OperationalConsistencyResult,
        facts: VerificationInput,
        verification: VerificationResult,
        risk: RiskResult,
        rag: RAGResult,
        constraints: EvidenceConstraints,
        summaries: dict[str, ToolExecutionSummaryItem],
        decision: LLMDecision | None,
        failure_notes: list[str] | None,
        llm_attempted: bool,
    ) -> AnalyzeOutcome:
        await self.deps.event_service.update_event_status(event_id, EventStatus.LLM_COMPLETED)
        final = self.deps.output_finalizer.finalize(
            metadata=FinalizationMetadata(
                event_id=event_id,
                request_id=request_id,
                video_id=request.video_id,
                observation_time_utc=context.observation_time_utc,
                observation_end_time_utc=context.observation_end_time_utc,
            ),
            visual=request.visual_evidence,
            context=context,
            platform=platform,
            permission=permission,
            notam=notam,
            inventory=inventory,
            consistency=consistency,
            facts=facts,
            verification=verification,
            risk=risk,
            rag=rag,
            constraints=constraints,
            action_catalog=self.deps.action_catalog,
            tool_execution_summary=summaries,
            model_versions=self.deps.model_versions,
            llm_decision=decision,
            failure_notes=failure_notes,
        )
        await self.deps.event_service.finalize_event(
            event_id, final.schema_version, final.model_dump(mode="json")
        )
        self.metrics.increment("event_success_rate")
        if llm_attempted and not await self.deps.event_service.has_other_active_video_event(
            request.video_id, event_id
        ):
            try:
                await self.deps.llm_client.unload()
                await self.deps.event_service.record_event_step(
                    event_id, "OLLAMA_UNLOAD", "SUCCESS"
                )
            except Exception:
                self.metrics.increment("ollama_unload_failure_rate")
                await self.deps.event_service.record_event_step(
                    event_id, "OLLAMA_UNLOAD", "WARNING", {"error_code": "UNLOAD_FAILED"}
                )
                self.logger.warning(
                    event_id=event_id,
                    request_id=request_id,
                    operation="ollama_unload",
                    error_code="UNLOAD_FAILED",
                )
        return AnalyzeOutcome(
            200,
            event_id,
            request_id,
            EventStatus.FINALIZED,
            final.model_dump(mode="json"),
        )

    async def _platform_tool_only(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        event_id: str,
        request_id: str,
    ) -> ToolResponseEnvelope[PlatformResult]:
        visual, record = request.visual_evidence, context.record
        return cast(
            ToolResponseEnvelope[PlatformResult],
            await self.deps.platform_factory(event_id, request_id).execute(
                PlatformToolRequest(
                    visual_class=visual.visual_class,
                    final_visual_hypothesis=visual.final_visual_hypothesis,
                    candidate_names=[item.candidate_name for item in visual.candidate_matches],
                    context_id=record.context_id if record else None,
                    context_status=context.context_status,
                ),
                timeout_seconds=0.2,
            ),
        )

    async def _eligible_downstream_tools(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        platform: ToolResponseEnvelope[PlatformResult],
        event_id: str,
        request_id: str,
    ) -> tuple[
        ToolResponseEnvelope[PermissionFlightPlanResult],
        ToolResponseEnvelope[NotamResult],
    ]:
        """Run downstream checks concurrently for a resolved platform and complete context."""
        permission_task = asyncio.create_task(
            self._permission_tool(context, platform, event_id, request_id)
        )
        notam_task = asyncio.create_task(
            self._notam_tool_only(request, context, platform, event_id, request_id)
        )
        permission, notam = await asyncio.gather(permission_task, notam_task)
        return permission, notam

    async def _notam_tool_only(
        self,
        request: AnalyzeEventRequest,
        context: ContextResolution,
        platform: ToolResponseEnvelope[PlatformResult],
        event_id: str,
        request_id: str,
    ) -> ToolResponseEnvelope[NotamResult]:
        """Run NOTAM only when all operational context facts are available."""
        record = context.record
        if (
            context.context_status is not ContextStatus.COMPLETE
            or record is None
            or record.operational_area_id is None
            or record.scenario_id is None
            or context.observation_time_utc is None
            or context.observation_end_time_utc is None
        ):
            return await self._empty_notam_skip(event_id, request_id, "CONTEXT_INCOMPLETE")
        platform_data = platform.data or PlatformResult(platform_status=PlatformStatus.UNKNOWN)
        return cast(
            ToolResponseEnvelope[NotamResult],
            await self.deps.notam_factory(event_id, request_id).execute(
                NotamToolRequest(
                    context_id=record.context_id,
                    operational_area_id=record.operational_area_id,
                    scenario_id=record.scenario_id,
                    observation_time_utc=context.observation_time_utc,
                    observation_end_time_utc=context.observation_end_time_utc,
                    visual_class=request.visual_evidence.visual_class,
                    platform_id=platform_data.platform_id,
                    context_status=context.context_status,
                    fir_code=record.fir_code,
                    aerodrome_code=record.aerodrome_code,
                    operation_lower_limit=record.operation_lower_limit,
                    operation_upper_limit=record.operation_upper_limit,
                ),
                timeout_seconds=0.5,
            ),
        )

    async def _permission_tool(
        self,
        context: ContextResolution,
        platform: ToolResponseEnvelope[PlatformResult],
        event_id: str,
        request_id: str,
    ) -> ToolResponseEnvelope[PermissionFlightPlanResult]:
        """Run Permission/Flight Plan only with complete operational context."""
        record = context.record
        if (
            context.context_status is not ContextStatus.COMPLETE
            or record is None
            or context.observation_time_utc is None
            or context.observation_end_time_utc is None
        ):
            return await self._empty_permission_skip(event_id, request_id, "CONTEXT_INCOMPLETE")
        data = platform.data or PlatformResult(platform_status=PlatformStatus.UNKNOWN)
        return cast(
            ToolResponseEnvelope[PermissionFlightPlanResult],
            await self.deps.permission_factory(event_id, request_id).execute(
                PermissionFlightPlanRequest(
                    platform_id=data.platform_id,
                    context_id=record.context_id,
                    operational_area_id=record.operational_area_id,
                    scenario_id=record.scenario_id,
                    observation_time_utc=context.observation_time_utc,
                    observation_end_time_utc=context.observation_end_time_utc,
                    context_status=context.context_status,
                    platform_execution_status=platform.execution_status,
                    platform_status=data.platform_status,
                ),
                timeout_seconds=0.5,
            ),
        )

    async def _empty_permission_skip(
        self,
        event_id: str,
        request_id: str,
        reason: str,
    ) -> ToolResponseEnvelope[PermissionFlightPlanResult]:
        """Audit a skipped downstream check without inventing domain data."""
        return cast(
            ToolResponseEnvelope[PermissionFlightPlanResult],
            await self._manual_empty_skip(
                event_id, request_id, "permission_flight_plan_tool", reason
            ),
        )

    async def _empty_notam_skip(
        self,
        event_id: str,
        request_id: str,
        reason: str,
    ) -> ToolResponseEnvelope[NotamResult]:
        """Audit a skipped downstream check without inventing domain data."""
        return cast(
            ToolResponseEnvelope[NotamResult],
            await self._manual_empty_skip(event_id, request_id, "notam_tool", reason),
        )

    async def _manual_empty_skip(
        self,
        event_id: str,
        request_id: str,
        tool_name: str,
        reason: str,
    ) -> ToolResponseEnvelope[BaseModel]:
        """Create and persist a reasoned SKIPPED envelope with no domain result."""
        now = utc_now()
        envelope = ToolResponseEnvelope[BaseModel](
            tool_name=tool_name,
            tool_version="1.0.0",
            event_id=event_id,
            request_id=request_id,
            execution_status=ToolExecutionStatus.SKIPPED,
            started_at_utc=now,
            finished_at_utc=now,
            latency_ms=0,
            warnings=[reason],
        )
        await self.deps.event_service.record_tool_execution(
            event_id=event_id,
            request_id=request_id,
            tool_name=tool_name,
            attempt_number=1,
            execution_status=ToolExecutionStatus.SKIPPED.value,
            domain_status=None,
            response=envelope.model_dump(mode="json"),
            latency_ms=0,
        )
        return envelope

    async def _early_envelopes(
        self, event_id: str, request_id: str
    ) -> tuple[
        ToolResponseEnvelope[PlatformResult],
        ToolResponseEnvelope[PermissionFlightPlanResult],
        ToolResponseEnvelope[NotamResult],
    ]:
        platform = await self._manual(
            event_id,
            request_id,
            "platform_tool",
            PlatformResult(platform_status=PlatformStatus.NON_AIRCRAFT),
            "STRONG_NON_AIRCRAFT",
        )
        permission = await self._manual(
            event_id,
            request_id,
            "permission_flight_plan_tool",
            PermissionFlightPlanResult(
                permission_status=PermissionStatus.NOT_APPLICABLE,
                flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
                record_consistency=RecordConsistency.NOT_APPLICABLE,
                skip_reason="STRONG_NON_AIRCRAFT",
            ),
            "STRONG_NON_AIRCRAFT",
        )
        notam = await self._manual(
            event_id,
            request_id,
            "notam_tool",
            NotamResult(
                notam_status=NotamStatus.NONE_ACTIVE,
                operation_effect=NotamOperationEffect.NO_EFFECT,
                skip_reason="STRONG_NON_AIRCRAFT",
            ),
            "STRONG_NON_AIRCRAFT",
        )
        return platform, permission, notam

    async def _manual_permission_skip(
        self, event_id: str, request_id: str, reason: str
    ) -> ToolResponseEnvelope[PermissionFlightPlanResult]:
        return await self._manual(
            event_id,
            request_id,
            "permission_flight_plan_tool",
            PermissionFlightPlanResult(
                permission_status=PermissionStatus.NOT_APPLICABLE,
                flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
                record_consistency=RecordConsistency.NOT_APPLICABLE,
                skip_reason=reason,
            ),
            reason,
        )

    async def _manual_notam_skip(
        self, event_id: str, request_id: str, reason: str
    ) -> ToolResponseEnvelope[NotamResult]:
        return await self._manual(
            event_id,
            request_id,
            "notam_tool",
            NotamResult(
                notam_status=NotamStatus.NONE_ACTIVE,
                operation_effect=NotamOperationEffect.NO_EFFECT,
                skip_reason=reason,
            ),
            reason,
        )

    async def _manual(
        self,
        event_id: str,
        request_id: str,
        tool_name: str,
        data: DataT,
        reason: str,
    ) -> ToolResponseEnvelope[DataT]:
        now = utc_now()
        envelope = ToolResponseEnvelope[DataT](
            tool_name=tool_name,
            tool_version="1.0.0",
            event_id=event_id,
            request_id=request_id,
            execution_status=ToolExecutionStatus.SKIPPED,
            started_at_utc=now,
            finished_at_utc=now,
            latency_ms=0,
            data=data,
            warnings=[reason],
        )
        await self.deps.event_service.record_tool_execution(
            event_id=event_id,
            request_id=request_id,
            tool_name=tool_name,
            attempt_number=1,
            execution_status=ToolExecutionStatus.SKIPPED.value,
            domain_status=self._domain_status(data),
            response=envelope.model_dump(mode="json"),
            latency_ms=0,
        )
        return envelope

    @staticmethod
    def _facts(
        request: AnalyzeEventRequest,
        context: ContextResolution,
        platform: ToolResponseEnvelope[PlatformResult],
        inventory: ToolResponseEnvelope[TurkeyInventoryResult],
        permission: ToolResponseEnvelope[PermissionFlightPlanResult],
        notam: ToolResponseEnvelope[NotamResult],
        consistency: OperationalConsistencyResult,
    ) -> VerificationInput:
        platform_data = platform.data or PlatformResult(platform_status=PlatformStatus.UNKNOWN)
        permission_data = permission.data or PermissionFlightPlanResult(
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
        )
        notam_data = notam.data or NotamResult(
            notam_status=NotamStatus.NONE_ACTIVE,
            operation_effect=NotamOperationEffect.UNKNOWN,
        )
        visual = request.visual_evidence
        return VerificationInput(
            context_status=context.context_status,
            platform_status=platform_data.platform_status,
            platform_usage_domain=platform_data.usage_domain,
            vlm_origin_category=classify_vlm_origin(visual.upstream_vlm_output.ulke_orjini),
            inventory_status=(
                inventory.data.inventory_status
                if inventory.data is not None
                else InventoryStatus.UNKNOWN
            ),
            operational_consistency_status=consistency.status,
            operational_consistency_flags=consistency.flags,
            permission_status=permission_data.permission_status,
            flight_plan_status=permission_data.flight_plan_status,
            record_consistency=permission_data.record_consistency,
            notam_status=notam_data.notam_status,
            notam_operation_effect=notam_data.operation_effect,
            visual_class=visual.visual_class,
            visual_evidence_status=visual.visual_evidence_status,
            visual_confidence=visual.visual_confidence,
            uncertainty_level=visual.uncertainty_level,
            visual_human_review_required=visual.human_visual_review_required,
            platform_execution_status=platform.execution_status,
            inventory_execution_status=inventory.execution_status,
            permission_execution_status=permission.execution_status,
            notam_execution_status=notam.execution_status,
        )

    def _constraints(
        self,
        facts: VerificationInput,
        verification: VerificationResult,
        risk: RiskResult,
        rag: RAGResult,
    ) -> EvidenceConstraints:
        return EvidenceConstraints(
            minimum_risk_level=risk.minimum_risk_level.value,
            human_review_required=risk.human_review_required,
            allowed_decision_codes=allowed_decision_codes(verification, facts),
            allowed_action_codes=allowed_action_codes(
                self.deps.action_catalog, risk, facts, verification
            ),
            allowed_source_ids=[source.source_id for source in rag.sources],
        )

    @staticmethod
    def _domain_status(data: BaseModel) -> str | None:
        for name in ("platform_status", "permission_status", "notam_status"):
            value = getattr(data, name, None)
            if value is not None:
                return str(value)
        return None

    @staticmethod
    def _summaries(
        platform: ToolResponseEnvelope[PlatformResult],
        permission: ToolResponseEnvelope[PermissionFlightPlanResult],
        notam: ToolResponseEnvelope[NotamResult],
    ) -> dict[str, ToolExecutionSummaryItem]:
        result: dict[str, ToolExecutionSummaryItem] = {}
        for envelope in (platform, permission, notam):
            result[envelope.tool_name] = ToolExecutionSummaryItem(
                execution_status=envelope.execution_status,
                latency_ms=envelope.latency_ms,
                domain_status=(
                    DecisionOrchestrator._domain_status(envelope.data)
                    if envelope.data is not None
                    else None
                ),
                error_code=envelope.error.code if envelope.error else None,
                warnings=envelope.warnings,
            )
        return result
