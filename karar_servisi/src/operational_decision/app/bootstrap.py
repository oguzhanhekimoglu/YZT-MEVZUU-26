"""Construct the local application dependency graph outside core logic."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from qdrant_client import QdrantClient

from operational_decision.app.config import AppSettings
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.health import ComponentHealth, HealthService, HealthStatus
from operational_decision.context.context_repository import ContextRepository
from operational_decision.context.context_resolver import OperationalContextResolver
from operational_decision.contracts.final_output import ModelVersions
from operational_decision.contracts.llm import LLMDecision
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
    TurkeyInventoryRegistry,
    TurkeyInventoryRegistryError,
    load_turkey_inventory_registry,
)
from operational_decision.llm.base_client import BaseLLMClient
from operational_decision.llm.response_parser import StructuredDecisionRunner
from operational_decision.llm.vllm_client import VLLMClient
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
from operational_decision.rag.chunker import QwenTokenCounter
from operational_decision.rag.document_catalog import DocumentCatalog
from operational_decision.rag.embedding_provider import RemoteEmbedProvider
from operational_decision.rag.qdrant_store import QdrantStore
from operational_decision.rag.retriever import TextRetriever
from operational_decision.tools.notam_tool import NotamTool
from operational_decision.tools.permission_flight_plan_tool import PermissionFlightPlanTool
from operational_decision.tools.platform_tool import PlatformTool
from operational_decision.tools.text_rag_tool import TextRAGTool
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool


async def _db_probe(database: OperationalDatabase | EventMemoryDatabase) -> ComponentHealth:
    try:
        async with database.connection() as connection:
            await (await connection.execute("SELECT 1")).fetchone()
    except Exception:
        return ComponentHealth(status=HealthStatus.FAILED, detail="DATABASE_UNAVAILABLE")
    return ComponentHealth(status=HealthStatus.HEALTHY)


def _constant_probe(result: ComponentHealth) -> Callable[[bool], Awaitable[ComponentHealth]]:
    async def probe(deep: bool) -> ComponentHealth:
        del deep
        return result

    return probe


def _vllm_probes(
    settings: AppSettings, client: VLLMClient
) -> tuple[
    Callable[[bool], Awaitable[ComponentHealth]],
    Callable[[bool], Awaitable[ComponentHealth]],
]:
    """EVREN/vLLM sağlık kontrolü — /v1/models'ı Bearer anahtarıyla sorgular."""

    headers = {"Authorization": f"Bearer {settings.vllm_api_key}"} if settings.vllm_api_key else None

    async def models() -> tuple[bool, bool]:
        try:
            async with httpx.AsyncClient(
                base_url=settings.vllm_base_url, timeout=5.0, headers=headers
            ) as http:
                response = await http.get("/v1/models")
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return False, False
        data = payload.get("data", []) if isinstance(payload, dict) else []
        ids = {item.get("id") for item in data if isinstance(item, dict)}
        return True, settings.decision_model in ids

    async def vllm_probe(deep: bool) -> ComponentHealth:
        del deep
        available, _ = await models()
        return ComponentHealth(
            status=HealthStatus.HEALTHY if available else HealthStatus.DEGRADED,
            detail=None if available else "VLLM_UNAVAILABLE",
        )

    async def model_probe(deep: bool) -> ComponentHealth:
        available, model_exists = await models()
        if not available:
            return ComponentHealth(status=HealthStatus.DEGRADED, detail="VLLM_UNAVAILABLE")
        if not model_exists:
            return ComponentHealth(status=HealthStatus.DEGRADED, detail="CANONICAL_MODEL_MISSING")
        if deep:
            try:
                raw = await client.generate(
                    [
                        {
                            "role": "user",
                            "content": (
                                "Return JSON with decision_code INDETERMINATE and a short "
                                "Turkish summary; use no actions or sources."
                            ),
                        }
                    ]
                )
                LLMDecision.model_validate_json(raw, strict=True)
            except Exception:
                return ComponentHealth(status=HealthStatus.DEGRADED, detail="DEEP_INFERENCE_FAILED")
        return ComponentHealth(status=HealthStatus.HEALTHY)

    return vllm_probe, model_probe


async def _seed_runtime_operational_data(
    database: OperationalDatabase, settings: AppSettings
) -> None:
    """Load DEMO_MOCK operational records only in explicit DEMO mode."""
    if settings.runtime_mode == "DEMO":
        await seed_operational_database(database, settings.seed_directory)


async def _assert_no_demo_mock_operational_data(database: OperationalDatabase) -> None:
    """Fail production startup when the selected DB contains demo operational rows."""
    tables = ("video_contexts", "permissions", "flight_plans", "notams")
    async with database.connection() as connection:
        for table in tables:
            row = await (
                await connection.execute(
                    f"SELECT 1 FROM {table} WHERE source_type = ? LIMIT 1",
                    ("DEMO_MOCK",),
                )
            ).fetchone()
            if row is not None:
                raise RuntimeError(f"PRODUCTION_DATABASE_CONTAINS_DEMO_MOCK:{table}")


async def build_application_container(
    settings: AppSettings | None = None,
) -> ApplicationContainer:
    """Initialize local DBs, tools, RAG, LLM, orchestrator, and health probes."""
    resolved = settings or AppSettings()
    operational_db = OperationalDatabase(resolved.operational_db_path)
    event_db = EventMemoryDatabase(resolved.event_db_path)
    await operational_db.initialize()
    await event_db.initialize()
    if resolved.runtime_mode == "PRODUCTION":
        await _assert_no_demo_mock_operational_data(operational_db)
    await _seed_runtime_operational_data(operational_db, resolved)
    event_service = EventService(event_db)
    await event_service.recover_interrupted_events()

    platform_registry = load_platform_registry(resolved.platform_registry_path)
    registry = PlatformRegistryIndex(
        platform_registry,
        load_platform_aliases(resolved.platform_aliases_path),
    )
    inventory_registry: TurkeyInventoryRegistry | None = None
    inventory_registry_error: TurkeyInventoryRegistryError | None = None
    if resolved.runtime_mode == "DEMO":
        inventory_registry = load_turkey_inventory_registry(
            resolved.turkey_inventory_registry_path,
            platform_registry,
        )
    else:
        inventory_registry_error = TurkeyInventoryRegistryError(
            "PRODUCTION_INVENTORY_PROVIDER_NOT_CONFIGURED"
        )
    context_resolver = OperationalContextResolver(ContextRepository(operational_db))
    permission_repository = PermissionRepository(operational_db)
    flight_plan_repository = FlightPlanRepository(operational_db)
    notam_repository = NotamRepository(operational_db)

    catalog: DocumentCatalog | None = None
    embedding: RemoteEmbedProvider | None = None
    retriever: TextRetriever | None = None
    rag_error: str | None = None
    try:
        catalog = DocumentCatalog(resolved.document_manifest_path)
        await asyncio.to_thread(catalog.validate)
        embedding = RemoteEmbedProvider(
            base_url=resolved.vllm_base_url, api_key=resolved.vllm_api_key
        )
        qdrant_client = QdrantClient(
            url=resolved.qdrant_url, port=443, prefix=resolved.qdrant_collection_prefix,
            api_key=resolved.qdrant_api_key, timeout=600,
        )
        rag_collection_name = f"{resolved.qdrant_collection_prefix}-mevzuu-text-rag"
        rag_store = await asyncio.to_thread(
            QdrantStore.connect, qdrant_client, rag_collection_name, embedding.dimension
        )
        retriever = await asyncio.to_thread(
            TextRetriever,
            catalog=catalog,
            embedding_provider=embedding,
            store=rag_store,
            index_dir=resolved.rag_index_dir,
        )
    except Exception as error:
        rag_error = type(error).__name__

    token_counter = QwenTokenCounter(resolved.embedding_model_path)
    llm_client: BaseLLMClient = VLLMClient(
        model=resolved.decision_model,
        base_url=resolved.vllm_base_url,
        api_key=resolved.vllm_api_key or None,
        timeout_seconds=1800.0,  # EVREN dokumantasyonu: chat completions icin zorunlu
    )

    def platform_factory(event_id: str, request_id: str) -> PlatformTool:
        return PlatformTool(
            registry,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )

    def inventory_factory(event_id: str, request_id: str) -> TurkeyInventoryTool:
        return TurkeyInventoryTool(
            inventory_registry,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
            registry_error=inventory_registry_error,
        )

    def permission_factory(event_id: str, request_id: str) -> PermissionFlightPlanTool:
        return PermissionFlightPlanTool(
            permission_repository,
            flight_plan_repository,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )

    def notam_factory(event_id: str, request_id: str) -> NotamTool:
        return NotamTool(
            notam_repository,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )

    def rag_factory(event_id: str, request_id: str) -> TextRAGTool:
        if retriever is None:
            raise RuntimeError("RAG is unavailable")
        return TextRAGTool(
            retriever=retriever,
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )

    dependencies = OrchestratorDependencies(
        event_service=event_service,
        context_resolver=context_resolver,
        platform_factory=platform_factory,
        inventory_factory=inventory_factory,
        permission_factory=permission_factory,
        notam_factory=notam_factory,
        rag_factory=rag_factory if retriever is not None else None,
        consistency_checker=OperationalConsistencyChecker(),
        verification_checker=VerificationChecker(),
        risk_advisor=RiskAdvisor.from_yaml(resolved.risk_rules_path),
        evidence_builder=EvidencePackageBuilder(token_counter),
        decision_runner=StructuredDecisionRunner(llm_client),
        llm_client=llm_client,
        output_finalizer=OutputFinalizer(),
        action_catalog=load_action_catalog(resolved.action_catalog_path),
        model_versions=ModelVersions(
            decision_llm=resolved.decision_model,
            text_embedding="bge-m3-embed",
        ),
        llm_enabled=resolved.llm_enabled,
    )
    assert isinstance(llm_client, VLLMClient)
    ollama_probe, model_probe = _vllm_probes(resolved, llm_client)
    rag_health = ComponentHealth(
        status=HealthStatus.HEALTHY if retriever is not None else HealthStatus.FAILED,
        detail=rag_error,
    )
    embedding_health = ComponentHealth(
        status=HealthStatus.HEALTHY if embedding is not None else HealthStatus.FAILED,
        detail=rag_error,
    )
    inventory_health = ComponentHealth(
        status=(
            HealthStatus.HEALTHY
            if inventory_registry is not None
            else HealthStatus.FAILED
        ),
        detail=(
            None
            if inventory_registry is not None
            else "PRODUCTION_INVENTORY_PROVIDER_NOT_CONFIGURED"
        ),
    )
    probes = {
        "operational_db": lambda deep: _db_probe(operational_db),
        "event_memory_db": lambda deep: _db_probe(event_db),
        "turkey_inventory_registry": _constant_probe(inventory_health),
        "platform_registry": _constant_probe(ComponentHealth(status=HealthStatus.HEALTHY)),
        "rag_index": _constant_probe(rag_health),
        "embedding_model": _constant_probe(embedding_health),
        "ollama": ollama_probe,
        "decision_model": model_probe,
    }
    health = HealthService(
        probes,
        {
            "operational_db",
            "event_memory_db",
            "platform_registry",
            "turkey_inventory_registry",
            "rag_index",
            "embedding_model",
        },
    )
    return ApplicationContainer(
        orchestrator=DecisionOrchestrator(dependencies),
        event_service=event_service,
        health_service=health,
        scenario_path=resolved.scenario_path,
        runtime_mode=resolved.runtime_mode,
    )
