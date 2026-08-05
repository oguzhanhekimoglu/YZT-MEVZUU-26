"""Runtime platform usage-domain fact tests."""
# ruff: noqa: D103

from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    ToolExecutionStatus,
    UncertaintyLevel,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.platform import (
    PlatformRegistry,
    PlatformToolRequest,
    UsageDomain,
)
from operational_decision.contracts.verification import VerificationInput
from operational_decision.decision.verification_checker import VerificationChecker
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)
from operational_decision.tools.platform_tool import PlatformTool

ROOT = Path(__file__).resolve().parents[2]


def registry() -> PlatformRegistryIndex:
    records = load_platform_registry(ROOT / "data/platforms/platform_registry.json")
    aliases = load_platform_aliases(ROOT / "data/platforms/platform_aliases.json")
    return PlatformRegistryIndex(records, aliases)


async def resolve(alias: str, visual_class: VisualClass = VisualClass.UNKNOWN_AIRCRAFT):
    return await PlatformTool(
        registry(), event_id=f"evt_{alias}", request_id=f"req_{alias}"
    ).execute(
        PlatformToolRequest(
            visual_class=visual_class,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_A",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alias", "platform_id"),
    [
        ("F-16", "PLT_F16"),
        ("F-35A", "PLT_F35A"),
        ("MQ-9 Reaper", "PLT_MQ9_REAPER"),
    ],
)
async def test_exact_registry_military_usage_domain(alias: str, platform_id: str) -> None:
    response = await resolve(alias)
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert response.data is not None
    assert response.data.platform_id == platform_id
    assert response.data.usage_domain is UsageDomain.MILITARY


@pytest.mark.asyncio
async def test_exact_registry_civil_usage_domain() -> None:
    response = await resolve("Boeing 747", VisualClass.CIVILIAN_AIRCRAFT)
    assert response.data is not None
    assert response.data.usage_domain is UsageDomain.CIVIL


@pytest.mark.asyncio
async def test_unresolved_platform_usage_domain_is_unknown() -> None:
    response = await resolve("Unregistered UAV", VisualClass.UAV)
    assert response.data is not None
    assert response.data.platform_status is PlatformStatus.UNKNOWN
    assert response.data.usage_domain is UsageDomain.UNKNOWN


def fixture_registry(usage_domain: UsageDomain) -> PlatformRegistryIndex:
    source = load_platform_registry(ROOT / "data/platforms/platform_registry.json")
    boeing = next(item for item in source.platforms if item.platform_id == "PLT_BOEING_747")
    assert boeing.taxonomy is not None
    fixture = boeing.model_copy(
        update={
            "platform_id": f"PLT_FIXTURE_{usage_domain.value}",
            "canonical_name": f"Fixture {usage_domain.value} UAV",
            "aliases": [f"Fixture {usage_domain.value} UAV"],
            "category": VisualClass.UAV,
            "taxonomy": boeing.taxonomy.model_copy(update={"usage_domain": usage_domain}),
        }
    )
    return PlatformRegistryIndex(
        PlatformRegistry(schema_version="platform-registry/1.1", platforms=[fixture])
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("usage_domain", [UsageDomain.DUAL_USE, UsageDomain.CIVIL])
async def test_uav_visual_class_does_not_promote_registry_usage_domain(
    usage_domain: UsageDomain,
) -> None:
    alias = f"Fixture {usage_domain.value} UAV"
    response = await PlatformTool(
        fixture_registry(usage_domain),
        event_id=f"evt_{usage_domain.value}",
        request_id=f"req_{usage_domain.value}",
    ).execute(
        PlatformToolRequest(
            visual_class=VisualClass.UAV,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_A",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert response.data is not None
    assert response.data.usage_domain is usage_domain
    assert response.data.usage_domain is not UsageDomain.MILITARY


def verification_facts(usage_domain: UsageDomain) -> VerificationInput:
    return VerificationInput(
        context_status=ContextStatus.COMPLETE,
        platform_status=PlatformStatus.EXPECTED,
        platform_usage_domain=usage_domain,
        permission_status=PermissionStatus.VALID,
        flight_plan_status=FlightPlanStatus.FILED,
        record_consistency=RecordConsistency.CONSISTENT,
        notam_status=NotamStatus.NONE_ACTIVE,
        notam_operation_effect=NotamOperationEffect.NO_EFFECT,
        visual_class=VisualClass.UAV,
        visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
        visual_confidence=0.9,
        uncertainty_level=UncertaintyLevel.LOW,
        visual_human_review_required=False,
        platform_execution_status=ToolExecutionStatus.SUCCESS,
        permission_execution_status=ToolExecutionStatus.SUCCESS,
        notam_execution_status=ToolExecutionStatus.SUCCESS,
    )


def test_platform_usage_domain_is_inert_in_verification_phase_one() -> None:
    checker = VerificationChecker()
    military = checker.check(verification_facts(UsageDomain.MILITARY))
    civil = checker.check(verification_facts(UsageDomain.CIVIL))
    dual_use = checker.check(verification_facts(UsageDomain.DUAL_USE))
    unknown = checker.check(verification_facts(UsageDomain.UNKNOWN))
    assert military == civil == dual_use == unknown
