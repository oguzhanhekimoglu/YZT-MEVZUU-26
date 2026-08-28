"""Explicit raw-Turkish-VLM to canonical visual adaptation."""

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from operational_decision.contracts.common import (
    ConfidenceOrigin,
    EvidenceSourceMode,
    UncertaintyLevel,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.raw_vlm import (
    RawVLMAdapterRequest,
    RawVLMAdapterResponse,
)
from operational_decision.contracts.request import AnalyzeEventRequest, GPUHandoff
from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput
from operational_decision.contracts.visual import (
    FinalVisualEvidencePackage,
    ProducerMetadata,
    TrackMetrics,
    TrackTiming,
    UpstreamTrackContext,
)
from operational_decision.input.raw_vlm_adapter import (
    adapt_raw_vlm_payload,
    normalize_raw_model_hypothesis,
    safe_vehicle_mapping_key,
)
from operational_decision.input.video_event_adapter import map_video_event_projection
from operational_decision.platform.platform_registry import PlatformRegistryIndex

DEFAULT_MAPPING_PATH = Path("config/visual_adapter.yaml")


def validate_upstream_vlm_payload(
    raw_payload: dict[str, object], platform_index: PlatformRegistryIndex | None = None
) -> UpstreamVLMOutput:
    """Validate a raw payload through the strict external JSON boundary."""
    return adapt_raw_vlm_payload(raw_payload, platform_index)


def load_vehicle_class_mapping(path: Path = DEFAULT_MAPPING_PATH) -> dict[str, VisualClass]:
    """Load and validate the only explicit Turkish class mapping table."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict) or content.get("schema_version") != "visual-adapter/1.0":
        raise ValueError("unsupported visual adapter mapping schema")
    raw_mapping = content.get("vehicle_class_mapping")
    if not isinstance(raw_mapping, dict):
        raise ValueError("vehicle_class_mapping must be an object")
    adapter = TypeAdapter(VisualClass)
    result: dict[str, VisualClass] = {}
    for raw_key, raw_value in raw_mapping.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise ValueError("visual adapter mappings must contain string pairs")
        result[raw_key] = adapter.validate_json(json.dumps(raw_value), strict=True)
    return result


def map_vlm_vehicle_class(value: str) -> VisualClass:
    """Map one raw Turkish class through the explicit configuration table."""
    mapping = load_vehicle_class_mapping()
    try:
        return mapping[value]
    except KeyError as exc:
        raise ValueError(f"unmapped upstream vehicle class: {value}") from exc


def normalize_vlm_model_hypothesis(value: str | None) -> str | None:
    """Convert a supplied model candidate into explicitly hypothetical wording."""
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if cleaned.casefold().endswith("-like"):
        return cleaned
    return f"{cleaned}-like"


def convert_percentage_confidence(value: int) -> float:
    """Convert validated integer percentage confidence to a 0–1 score."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError("confidence percentage must be an integer from 0 to 100")
    return round(value / 100.0, 4)


def map_upstream_vlm_to_canonical(
    *,
    raw_vlm: UpstreamVLMOutput,
    track_context: UpstreamTrackContext,
    producer_metadata: ProducerMetadata,
) -> FinalVisualEvidencePackage:
    """Build a conservative VLM-only package without inventing semantic facts."""
    visual_class = map_vlm_vehicle_class(raw_vlm.arac_sinifi)
    hypothesis = normalize_vlm_model_hypothesis(raw_vlm.hedef_modeli)
    if hypothesis is None and visual_class in {
        VisualClass.UNKNOWN_AIRCRAFT,
        VisualClass.HELICOPTER,
    }:
        hypothesis = visual_class.value
    if visual_class is not VisualClass.NON_AIRCRAFT and hypothesis is None:
        raise ValueError("aircraft VLM output requires hedef_modeli for canonical adaptation")
    return FinalVisualEvidencePackage(
        evidence_source_mode=EvidenceSourceMode.VLM_ONLY,
        track_id=track_context.track_id,
        visual_class=visual_class,
        final_visual_hypothesis=hypothesis,
        candidate_matches=[],
        visual_evidence_status=VisualEvidenceStatus.PARTIALLY_SUPPORTED,
        visual_confidence=convert_percentage_confidence(raw_vlm.guven_skoru),
        confidence_origin=ConfidenceOrigin.VLM_SELF_REPORTED,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        uncertainty_flags=["VLM_ONLY_NO_RETRIEVAL_CONFIRMATION"],
        human_visual_review_required=True,
        track_metrics=TrackMetrics(
            track_duration_seconds=track_context.track_duration_seconds,
            track_stability=track_context.track_stability,
            detection_count=track_context.detection_count,
            average_detection_confidence=track_context.average_detection_confidence,
        ),
        crop_evidence_summary=None,
        timing=TrackTiming(
            first_seen_offset_seconds=track_context.first_seen_offset_seconds,
            last_seen_offset_seconds=track_context.last_seen_offset_seconds,
        ),
        upstream_vlm_output=raw_vlm,
        producer_metadata=producer_metadata,
    )


def adapt_friend_raw_vlm_to_request(
    adapter_input: RawVLMAdapterRequest,
    *,
    adapted_at_utc: datetime | None = None,
    platform_index: PlatformRegistryIndex | None = None,
) -> RawVLMAdapterResponse:
    """Build one VLM-only canonical request without changing decision semantics."""
    raw = adapter_input.raw_vlm
    raw_payload = raw.model_dump(mode="python", by_alias=True)
    mapping_key = safe_vehicle_mapping_key(raw_payload, platform_index) or raw.arac_sinifi
    visual_class = map_vlm_vehicle_class(mapping_key)
    hypothesis = normalize_raw_model_hypothesis(raw.hedef_modeli)
    if hypothesis is None and visual_class is not VisualClass.NON_AIRCRAFT:
        hypothesis = visual_class.value

    helper_metadata = raw.helper_metadata()
    event_projection = map_video_event_projection(
        raw.video_events,
        visual_assessment_tr=raw.gorsel_analiz,
    )
    conflict = raw.conflict_detected
    # BUG-FIX (kök neden araştırması — "risk analizindeki belirsizlik sinyali
    # sağlıklı değil"): eskiden uncertainty_level yalnızca ikiliydi (MEDIUM
    # varsayılan, VLM kendi metniyle kendi sınıflandırmasıyla çelişirse HIGH) -
    # VRAG/VLM'in birbirini ne kadar güçlü doğruladığı (oy oranı) hiç
    # kullanılmıyordu. "_vrag_oy_orani" pipeline.py'den "_" ile başlayan bir
    # yardımcı alan olarak geliyor (RawVLMOutput zaten bunu extra=allow ile
    # kabul ediyor, ayrı bir şema değişikliği gerekmedi) - burada gerçek bir
    # 3 seviyeli belirsizlik sinyaline çevriliyor.
    vrag_oy_orani = helper_metadata.get("_vrag_oy_orani")
    vrag_oy_orani = vrag_oy_orani if isinstance(vrag_oy_orani, (int, float)) else None
    uncertainty_flags = ["VLM_ONLY_NO_RETRIEVAL_CONFIRMATION"]
    if conflict:
        uncertainty_flags.append("RAW_VLM_CONFLICT_REPORTED")
    if vrag_oy_orani is not None and vrag_oy_orani < 0.65:
        uncertainty_flags.append("VRAG_VOTE_SHARE_WEAK")
    if conflict or (vrag_oy_orani is not None and vrag_oy_orani < 0.65):
        uncertainty_level = UncertaintyLevel.HIGH
    elif vrag_oy_orani is not None and vrag_oy_orani >= 0.85:
        uncertainty_level = UncertaintyLevel.LOW
    else:
        uncertainty_level = UncertaintyLevel.MEDIUM

    upstream_audit = UpstreamVLMOutput(
        arac_sinifi=mapping_key,
        tehdit_seviyesi=raw.tehdit_seviyesi,
        tahmini_hedef_tipi=raw.tahmini_hedef_tipi,
        ulke_orjini=raw.ulke_orjini,
        hedef_modeli=raw.hedef_modeli,
        gidis_yeri=None,
        gorsel_analiz=raw.gorsel_analiz,
        guven_skoru=round(adapter_input.visual_confidence * 100),
    )
    visual = FinalVisualEvidencePackage(
        evidence_source_mode=EvidenceSourceMode.VLM_ONLY,
        track_id=adapter_input.track_id,
        visual_class=visual_class,
        final_visual_hypothesis=hypothesis,
        candidate_matches=[],
        visual_evidence_status=VisualEvidenceStatus.PARTIALLY_SUPPORTED,
        visual_confidence=adapter_input.visual_confidence,
        confidence_origin=ConfidenceOrigin.VLM_SELF_REPORTED,
        uncertainty_level=uncertainty_level,
        uncertainty_flags=uncertainty_flags,
        human_visual_review_required=True,
        track_metrics=None,
        crop_evidence_summary=None,
        timing=TrackTiming(
            first_seen_offset_seconds=adapter_input.first_seen_offset_seconds,
            last_seen_offset_seconds=adapter_input.last_seen_offset_seconds,
        ),
        upstream_vlm_output=upstream_audit,
        video_event_projection=event_projection,
        producer_metadata=ProducerMetadata(
            visual_pipeline_version="raw-vlm-adapter/1.0",
            vlm_model="UPSTREAM_PROVIDED",
            retrieval_model=None,
            created_at_utc=adapted_at_utc or datetime.now(UTC),
        ),
    )
    analyze_request = AnalyzeEventRequest(
        video_id=adapter_input.video_id,
        explanation_requested=False,
        gpu_handoff=GPUHandoff(
            visual_pipeline_status="COMPLETED",
            gpu_release_status="RELEASED",
        ),
        visual_evidence=visual,
        request_metadata={
            "source_type": "RAW_VLM_ADAPTER",
            "upstream_visual_threat_hypothesis": raw.tehdit_seviyesi,
            "visual_origin_hypothesis": raw.ulke_orjini,
            "raw_vlm_helper_metadata": helper_metadata,
            "video_event_projection": event_projection.model_dump(mode="json"),
        },
    )
    return RawVLMAdapterResponse(
        raw_vlm=raw.model_dump(mode="json", by_alias=True),
        helper_metadata=helper_metadata,
        video_event_projection=event_projection,
        analyze_request=analyze_request,
    )
