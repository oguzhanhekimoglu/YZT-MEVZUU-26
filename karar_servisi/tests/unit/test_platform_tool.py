"""Unit tests for exact platform matching."""
# ruff: noqa: D102, D103, D107

from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    PlatformStatus,
    ToolExecutionStatus,
    VisualClass,
)
from operational_decision.contracts.platform import (
    PlatformToolRequest,
)
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


@pytest.mark.asyncio
async def test_exact_alias_and_context_expectation() -> None:
    tool = PlatformTool(registry(), event_id="evt_1", request_id="req_1")
    response = await tool.execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="  f16 ",
            context_id="DEMO_CONTEXT_B",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert response.data is not None
    assert response.data.platform_id == "PLT_F16"
    assert response.data.platform_status is PlatformStatus.NOT_EXPECTED


@pytest.mark.asyncio
async def test_no_fuzzy_match_and_inactive_registry_is_ignored() -> None:
    tool = PlatformTool(registry(), event_id="evt_1", request_id="req_1")
    fuzzy = await tool.execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="F 16",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    inactive = await tool.execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="INACTIVE-AIRCRAFT",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert fuzzy.data is not None and fuzzy.data.platform_status is PlatformStatus.UNKNOWN
    assert inactive.data is not None and inactive.data.platform_id is None


@pytest.mark.asyncio
async def test_candidate_unique_ambiguity_and_contextless_resolution() -> None:
    tool = PlatformTool(registry(), event_id="evt_1", request_id="req_1")
    unique = await tool.execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            candidate_names=["unknown", "F-16"],
            context_status=ContextStatus.MISSING,
        ),
        timeout_seconds=1,
    )
    assert unique.data is not None
    assert unique.data.platform_id == "PLT_F16"
    assert unique.data.platform_status is PlatformStatus.IDENTIFIED_CONTEXT_UNKNOWN

    ambiguous = await tool.execute(
        PlatformToolRequest(
            visual_class=VisualClass.UNKNOWN_AIRCRAFT,
            candidate_names=["F-16", "Boeing 747"],
            context_id="DEMO_CONTEXT_A",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert ambiguous.data is not None
    assert ambiguous.data.platform_status is PlatformStatus.AMBIGUOUS


@pytest.mark.asyncio
async def test_non_aircraft_short_circuit() -> None:
    result = await PlatformTool(registry(), event_id="evt_1", request_id="req_1").execute(
        PlatformToolRequest(
            visual_class=VisualClass.NON_AIRCRAFT,
            context_status=ContextStatus.MISSING,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.NON_AIRCRAFT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    ["Boeing 747", "B747", "Boeing-747", "Boeing 747-like", "  b747  "],
)
async def test_boeing_747_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_b747", request_id="req_b747").execute(
        PlatformToolRequest(
            visual_class=VisualClass.CIVILIAN_AIRCRAFT,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_D",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_BOEING_747"
    assert result.data.matched_platform == "Boeing 747"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broad_alias",
    ["Boeing", "747", "Jumbo", "Passenger Aircraft", "Airliner"],
)
async def test_boeing_747_broad_aliases_are_not_registered(broad_alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_b747", request_id="req_b747").execute(
        PlatformToolRequest(
            visual_class=VisualClass.CIVILIAN_AIRCRAFT,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_D",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    ["Bayraktar TB2", "Bayraktar TB-2", "TB2", "TB-2", "Bayraktar TB2-like"],
)
async def test_bayraktar_tb2_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_tb2", request_id="req_tb2").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_E",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_BAYRAKTAR_TB2"
    assert result.data.matched_platform == "Bayraktar TB2"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("broad_alias", ["Bayraktar", "Drone", "İHA", "SİHA", "UAV", "UCAV"])
async def test_bayraktar_tb2_broad_aliases_are_not_registered(broad_alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_tb2", request_id="req_tb2").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_E",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias",
    ["Bayraktar AKINCI", "AKINCI", "Bayraktar Akıncı", "Akıncı", "Bayraktar AKINCI-like"],
)
async def test_bayraktar_akinci_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_akinci", request_id="req_akinci").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_F",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_BAYRAKTAR_AKINCI"
    assert result.data.matched_platform == "Bayraktar AKINCI"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("broad_alias", ["Bayraktar", "İHA", "SİHA", "UAV", "UCAV", "Heavy UAV"])
async def test_bayraktar_akinci_broad_aliases_are_not_registered(
    broad_alias: str,
) -> None:
    result = await PlatformTool(registry(), event_id="evt_akinci", request_id="req_akinci").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_F",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["TUSAŞ ANKA", "TUSAS ANKA", "ANKA", "Anka", "TUSAŞ ANKA-like"])
async def test_tusas_anka_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_anka", request_id="req_anka").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UAV,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_G",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_TUSAS_ANKA"
    assert result.data.matched_platform == "TUSAŞ ANKA"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("broad_alias", ["TUSAŞ", "TUSAS", "İHA", "SİHA", "UAV", "MALE UAV"])
async def test_tusas_anka_broad_aliases_are_not_registered(broad_alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_anka", request_id="req_anka").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UAV,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_G",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["F-35A Lightning II", "F-35A", "F35A", "F-35A-like"])
async def test_f35a_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_f35a", request_id="req_f35a").execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_H",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_F35A"
    assert result.data.matched_platform == "F-35A Lightning II"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("family_alias", ["F-35", "F35", "F-35 Lightning II", "F-35-like"])
async def test_generic_f35_aliases_resolve_to_family_without_promoting_a_variant(
    family_alias: str,
) -> None:
    """A bare F-35 mention resolves to the family record, never to a specific A/B/C variant."""
    result = await PlatformTool(
        registry(), event_id="evt_f35_family", request_id="req_f35_family"
    ).execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis=family_alias,
            context_id="DEMO_CONTEXT_H",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_F35_GENERIC"
    assert result.data.platform_id not in {"PLT_F35A", "PLT_F35B", "PLT_F35C"}
    assert result.data.matched_platform == "F-35 Lightning II"


@pytest.mark.asyncio
@pytest.mark.parametrize("broad_alias", ["Lightning", "Fighter", "Savaş uçağı", "Aircraft"])
async def test_generic_fighter_aliases_are_not_registered(broad_alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_f35a", request_id="req_f35a").execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_H",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["MQ-9 Reaper", "MQ-9", "MQ9", "MQ-9 Reaper-like"])
async def test_mq9_reaper_controlled_exact_aliases(alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_mq9", request_id="req_mq9").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=alias,
            context_id="DEMO_CONTEXT_I",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.execution_status is ToolExecutionStatus.SUCCESS
    assert result.data is not None
    assert result.data.platform_id == "PLT_MQ9_REAPER"
    assert result.data.matched_platform == "MQ-9 Reaper"
    assert result.data.platform_status is PlatformStatus.EXPECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("broad_alias", ["Reaper", "İHA", "SİHA", "UAV", "UCAV", "Drone"])
async def test_mq9_reaper_broad_aliases_are_not_registered(broad_alias: str) -> None:
    result = await PlatformTool(registry(), event_id="evt_mq9", request_id="req_mq9").execute(
        PlatformToolRequest(
            visual_class=VisualClass.UCAV,
            final_visual_hypothesis=broad_alias,
            context_id="DEMO_CONTEXT_I",
            context_status=ContextStatus.COMPLETE,
        ),
        timeout_seconds=1,
    )
    assert result.data is not None
    assert result.data.platform_status is PlatformStatus.UNKNOWN
    assert result.data.platform_id is None
