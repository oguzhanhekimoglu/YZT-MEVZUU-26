"""HTTP endpoints for raw VLM adaptation and context-free assessment."""

from fastapi import APIRouter

from operational_decision.app.config import AppSettings
from operational_decision.contracts.raw_vlm import (
    RawVLMAdapterRequest,
    RawVLMAdapterResponse,
    RawVLMOutput,
)
from operational_decision.contracts.raw_vlm_assessment import RawVLMAssessmentResult
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)

router = APIRouter()


@router.post(
    "/api/v1/adapters/raw-vlm",
    response_model=RawVLMAdapterResponse,
)
async def adapt_raw_vlm(payload: RawVLMAdapterRequest) -> RawVLMAdapterResponse:
    """Expose deterministic adaptation without invoking operational decision logic.

    BUG-FIX: platform_index verilmeden çağrılıyordu — bu yüzden Registry'deki
    (Kaan dahil) 98+ platform hiç aranmıyor, adapt_friend_raw_vlm_to_request
    sessizce eski dar regex'e (yalnızca F-16/F-35) düşüyordu.
    """
    settings = AppSettings()
    platform_registry = load_platform_registry(settings.platform_registry_path)
    platform_index = PlatformRegistryIndex(
        platform_registry,
        load_platform_aliases(settings.platform_aliases_path),
    )
    return adapt_friend_raw_vlm_to_request(payload, platform_index=platform_index)


@router.post(
    "/api/v1/analyze/raw-vlm",
    response_model=RawVLMAssessmentResult,
)
async def analyze_raw_vlm_only(payload: RawVLMOutput) -> RawVLMAssessmentResult:
    """Assess platform, Registry origin, and Inventory without synthetic context."""
    settings = AppSettings()
    return assess_raw_vlm(
        payload,
        platform_registry_path=settings.platform_registry_path,
        platform_aliases_path=settings.platform_aliases_path,
        inventory_path=(
            settings.turkey_inventory_registry_path
            if settings.runtime_mode == "DEMO"
            else None
        ),
    )